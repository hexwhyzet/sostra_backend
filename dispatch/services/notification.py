import os
from concurrent.futures import ThreadPoolExecutor
from itertools import chain

from django.db import close_old_connections

from dispatch.services.access import dispatch_admins
from dispatch.services.duties import get_duty_point_participants
from myapp.utils import send_fcm_notification
from users.models import Notification


try:
    _NOTIFICATION_SEND_WORKERS = max(1, int(os.getenv("NOTIFICATION_SEND_WORKERS", "4")))
except ValueError:
    _NOTIFICATION_SEND_WORKERS = 4
_NOTIFICATION_EXECUTOR = ThreadPoolExecutor(max_workers=_NOTIFICATION_SEND_WORKERS)


def _send_notification_async(user, title, text):
    close_old_connections()
    try:
        send_fcm_notification(user, title, text)
    finally:
        close_old_connections()


def _enqueue_notification(user, title, text):
    try:
        _NOTIFICATION_EXECUTOR.submit(_send_notification_async, user, title, text)
    except Exception:
        # Fallback to sync if the executor is unavailable
        send_fcm_notification(user, title, text)


def create_notification(user, title, text, source, duty_action=None):
    return Notification.objects.create(
        user=user, title=title, text=text, source=source, duty_action=duty_action
    )


def create_and_notify(user, title, text, source, duty_action=None):
    notification = create_notification(
        user, title, text, source, duty_action=duty_action
    )
    _enqueue_notification(user, notification.title, notification.text)
    return notification


def notify_users(users, title, text, source, duty_action=None):
    notifications = []
    for point_admin in users:
        notification = create_notification(
            point_admin, title, text, source, duty_action=duty_action
        )
        _enqueue_notification(point_admin, notification.title, notification.text)
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
