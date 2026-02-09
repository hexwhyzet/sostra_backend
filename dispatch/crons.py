# dispatch/cron.py
from datetime import timedelta, datetime, date

from dispatch.calendar_ru import get_non_working_ranges
from dispatch.models import DutyRole, DutyPoint, WeekendDutyAssignment, Duty
from dispatch.services.access import dispatch_admins
from dispatch.services.duties import (
    get_current_duties,
    get_duty_point_by_duty_role,
    get_duties_by_date,
    get_or_create_duty,
    duty_overlaps_range,
    get_or_create_duty_range,
)
from dispatch.services.notification import create_and_notify, notify_users, notify_point_admins
from dispatch.utils import now, today
from users.models import NotificationSourceEnum


def need_to_open_notification():
    print(f"CRON PING {datetime.now()}")

    duties = get_current_duties(now(), start_offset=30)

    for duty in duties:
        print(duty)
        if not duty.is_opened and duty.notification_duty_is_coming is None:
            title = "Вам назначено дежурство сегодня"
            text = f"Дежурство в роли: {duty.role.name}"
            duty.notification_duty_is_coming = create_and_notify(duty.user, title, text, NotificationSourceEnum.DISPATCH.value)
            duty.save()

        # Повторное уведомление через 15 минут после первого, если дежурство еще не принято
        if (not duty.is_opened 
                and duty.notification_duty_is_coming is not None 
                and duty.notification_duty_reminder is None
                and now() - duty.notification_duty_is_coming.created_at > timedelta(minutes=15)):
            title = "Напоминание: не забудьте принять дежурство"
            text = f"Дежурство в роли: {duty.role.name} еще не принято. Пожалуйста, откройте дежурство в приложении."
            duty.notification_duty_reminder = create_and_notify(duty.user, title, text, NotificationSourceEnum.DISPATCH.value)
            duty.save()

        # Автоматическое открытие дежурства через 15 минут после напоминания, если дежурство еще не принято
        if (not duty.is_opened and duty.notification_need_to_open is None
                and duty.notification_duty_reminder is not None
                and now() - duty.notification_duty_reminder.created_at > timedelta(minutes=15)):
            duty.is_opened = True
            duty.is_forced_opened = True
            duty.notification_need_to_open = create_and_notify(
                duty.user,
                "Дежурство начато автоматически",
                f"Дежурство в роли: {duty.role.name}",
                NotificationSourceEnum.DISPATCH.value,
            )
            duty.save()

            admins = list(dispatch_admins())
            for point in get_duty_point_by_duty_role(duty.role):
                admins.extend(point.admins.all())

            notify_users(
                admins,
                f"Пользователь {duty.user.display_name} не начал дежурство",
                f"Пользователь {duty.user.display_name} не начал дежурство в роли {duty.role.name}, оно было открыто автоматически.",
                NotificationSourceEnum.DISPATCH.value,
            )


def check_missing_duties():
    """Проверяет отсутствующие дежурства на ближайшие 3 дня и уведомляет админов"""
    print(f"Checking missing duties {datetime.now()}")
    
    today_date = today()
    check_end_date = today_date + timedelta(days=3)
    
    # Получаем все точки дежурств
    duty_points = DutyPoint.objects.all()
    
    for point in duty_points:
        missing_days = []
        roles_to_check = []
        
        # Собираем все роли для этой точки
        if point.level_1_role:
            roles_to_check.append(point.level_1_role)
        if point.level_2_role:
            roles_to_check.append(point.level_2_role)
        if point.level_3_role:
            roles_to_check.append(point.level_3_role)
        
        # Проверяем каждую роль на наличие дежурств в ближайшие 3 дня
        for role in roles_to_check:
            current_date = today_date
            while current_date <= check_end_date:
                duties = get_duties_by_date(current_date, role)
                if not duties.exists():
                    missing_days.append((current_date, role))
                current_date += timedelta(days=1)
        
        # Если есть хотя бы один день без дежурства, уведомляем админов точки
        if missing_days:
            missing_info = []
            for missing_date, missing_role in missing_days:
                missing_info.append(f"{missing_date.strftime('%d.%m.%Y')} - {missing_role.name}")
            
            title = f"Отсутствуют дежурства в системе {point.name}"
            text = f"В ближайшие 3 дня не назначены дежурства:\n" + "\n".join(missing_info)
            
            notify_point_admins(
                point,
                title,
                text,
                NotificationSourceEnum.DISPATCH.value,
            )


def ensure_weekend_duties(days_ahead: int = 10):
    """
    Раз в сутки проверяет: если в ближайшие N дней есть нерабочие дни (по производственному
    календарю России) без дежурств, автоматически создаёт одно непрерывное дежурство на каждый
    период подряд идущих нерабочих дней по назначениям WeekendDutyAssignment.
    Если для роли не задано назначение — уведомляет dispatch-админов.
    """
    start_date = today()
    end_date = start_date + timedelta(days=max(days_ahead, 1) - 1)

    roles_to_check = set()
    for point in DutyPoint.objects.all().only("level_1_role", "level_2_role", "level_3_role"):
        if point.level_1_role_id:
            roles_to_check.add(point.level_1_role_id)
        if point.level_2_role_id:
            roles_to_check.add(point.level_2_role_id)
        if point.level_3_role_id:
            roles_to_check.add(point.level_3_role_id)

    if not roles_to_check:
        return []

    roles = list(DutyRole.objects.filter(id__in=roles_to_check).only("id"))
    assignments = list(
        WeekendDutyAssignment.objects.filter(is_active=True, role_id__in=roles_to_check)
        .select_related("role", "user")
        .only("role_id", "user_id")
        .order_by("role_id", "id")
    )
    assignment_by_role = {}
    for a in assignments:
        if a.role_id not in assignment_by_role:
            assignment_by_role[a.role_id] = a

    ranges = get_non_working_ranges(start_date, end_date)
    created = []
    missing_assignments = []

    for range_start, range_end in ranges:
        for role in roles:
            if duty_overlaps_range(role, range_start, range_end):
                continue
            assignment = assignment_by_role.get(role.id)
            if assignment is None:
                missing_assignments.append((range_start, range_end, role.id))
                continue
            duty, duty_created = get_or_create_duty_range(
                range_start,
                range_end,
                assignment.role,
                defaults={"user": assignment.user},
            )
            if duty_created:
                created.append(duty)

    if missing_assignments:
        role_map = {
            r.id: r
            for r in DutyRole.objects.filter(
                id__in=[rid for _, _, rid in missing_assignments]
            ).only("id", "name")
        }
        lines = []
        for range_start, range_end, role_id in missing_assignments:
            role_name = (
                role_map.get(role_id).name if role_id in role_map else f"роль {role_id}"
            )
            if range_start == range_end:
                lines.append(f"{range_start.strftime('%d.%m.%Y')} — {role_name}")
            else:
                lines.append(
                    f"{range_start.strftime('%d.%m.%Y')} – {range_end.strftime('%d.%m.%Y')} — {role_name}"
                )
        notify_users(
            list(dispatch_admins()),
            "Не настроены дежурные на нерабочие дни",
            "Для следующих периодов не задано назначение:\n" + "\n".join(lines),
            NotificationSourceEnum.DISPATCH.value,
        )

    return created
