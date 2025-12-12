# dispatch/cron.py
from datetime import timedelta, datetime

from dispatch.services.access import dispatch_admins
from dispatch.services.duties import get_current_duties, get_duty_point_by_duty_role
from dispatch.services.notification import create_and_notify, notify_users
from dispatch.utils import now
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

        if (not duty.is_opened and duty.notification_need_to_open is None
                and now() - duty.start_datetime > timedelta(minutes=15)):
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
