from itertools import chain

from dispatch.services.access import dispatch_admins
from dispatch.services.duties import get_duty_point_participants
from myapp.utils import send_fcm_notification
from users.models import Notification


def create_notification(user, title, text, source, duty_action=None):
    return Notification.objects.create(
        user=user, title=title, text=text, source=source, duty_action=duty_action
    )


def create_and_notify(user, title, text, source, duty_action=None):
    notification = create_notification(
        user, title, text, source, duty_action=duty_action
    )
    send_fcm_notification(user, notification.title, notification.text)
    return notification


def notify_users(users, title, text, source, duty_action=None):
    notifications = []
    for point_admin in users:
        notification = create_notification(
            point_admin, title, text, source, duty_action=duty_action
        )
        send_fcm_notification(point_admin, notification.title, notification.text)
        notifications.append(notification)
    return notifications


def notify_point_admins(point, title, text, source, duty_action=None):
    notify_users(
        {u for u in chain(point.admins.all(), dispatch_admins())},
        title,
        text,
        source,
        duty_action=duty_action,
    )


def notify_duty_point_participants(point, title, text, source, duty_action=None):
    """
    Отправляет уведомление всем участникам системы дежурства (уровни 0–3 и ответственные лица).
    Уведомления сохраняются в истории (Notification).
    """
    if point is None:
        return []
    participants = get_duty_point_participants(point)
    return notify_users(list(participants), title, text, source, duty_action=duty_action)


def notify_admins(title, text, source):
    notify_users(dispatch_admins(), title, text, source)
