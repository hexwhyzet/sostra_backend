from django.db.models import Q

from dispatch.models import Incident, IncidentStatusEnum, DutyPoint, Duty
from dispatch.services.duties import get_current_duties
from dispatch.services.messages import create_escalation_error_message_duty_not_opened, create_escalation_message
from dispatch.services.notification import notify_point_admins, notify_duty_point_participants, create_and_notify
from dispatch.utils import now
from myapp.admin import user_has_group
from myapp.custom_groups import DispatchAdminManager
from myproject.settings import AUTH_USER_MODEL
from users.models import NotificationSourceEnum


def escalate_incident(incident: Incident, escalation_author: AUTH_USER_MODEL):
    current_datetime = now()
    for i in range(min(incident.level + 1, 4), 5):
        if i == 4:
            create_escalation_message(incident, i, escalation_author, None)
            incident.level = i
            incident.is_critical = True
            incident.responsible_user = None
            if incident.point:
                notify_duty_point_participants(
                    incident.point,
                    incident.name,
                    f"Инцидент повышен до критического уровня (уровень 4). Пользователь: {escalation_author.display_name}.",
                    NotificationSourceEnum.DISPATCH.value,
                )
            continue

        duty_role = getattr(incident.point, f"level_{i}_role")
        if duty_role is None:
            continue
        duty = get_current_duties(current_datetime, role=duty_role).first()
        if duty is None:
            continue
        if not duty.is_opened:
            create_escalation_error_message_duty_not_opened(incident, i, duty)
            continue
        incident.level = i
        incident.responsible_user = duty.user
        incident.status = IncidentStatusEnum.WAITING_TO_BE_ACCEPTED.value
        if incident.responsible_user is not None:
            create_and_notify(
                incident.responsible_user,
                incident.name,
                f"Вам поручен инцидент на точке {incident.point.name}",
                NotificationSourceEnum.DISPATCH.value,
            )
            notify_point_admins(
                incident.point,
                incident.name,
                f"Инцидент был повышен до уровня {incident.level}",
                NotificationSourceEnum.DISPATCH.value,
            )
            notify_duty_point_participants(
                incident.point,
                incident.name,
                f"Инцидент передан дежурному уровня {incident.level}. Пользователь: {escalation_author.display_name}.",
                NotificationSourceEnum.DISPATCH.value,
            )
        create_escalation_message(incident, i, escalation_author, duty)
        break

    incident.save()


def user_incidents(user: AUTH_USER_MODEL):
    if user_has_group(user, DispatchAdminManager):
        return Incident.objects.select_related("author", "responsible_user", "point").all()

    exploitation_role_ids = user.exploitation_roles.values_list("id", flat=True)
    role_ids = Duty.objects.filter(user=user).values_list("role_id", flat=True).distinct()
    point_ids = DutyPoint.objects.filter(
        Q(admins=user)
        | Q(level_0_role_id__in=exploitation_role_ids)
        | Q(level_1_role_id__in=role_ids)
        | Q(level_2_role_id__in=role_ids)
        | Q(level_3_role_id__in=role_ids)
    ).values_list("id", flat=True).distinct()

    return (
        Incident.objects.filter(
            Q(author_id=user.id)
            | Q(responsible_user_id=user.id)
            | Q(point_id__in=point_ids)
        )
        .select_related("author", "responsible_user", "point")
    )
