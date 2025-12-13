from itertools import chain

from dispatch.services.access import dispatch_admins
from myapp.utils import send_fcm_notification
from users.models import Notification


def create_notification(user, title, text, source):
    return Notification.objects.create(user=user, title=title, text=text, source=source)


def create_and_notify(user, title, text, source):
    notification = create_notification(user, title, text, source)
    # send_fcm_notification(user, notification.title, notification.text)
    return notification


def notify_users(users, title, text, source):
    notifications = []
    for point_admin in users:
        notification = create_notification(point_admin, title, text, source)
        send_fcm_notification(point_admin, notification.title, notification.text)
        notifications.append(notification)
    return notifications


def notify_point_admins(point, title, text, source):
    notify_users(
        {u for u in chain(point.admins.all(), dispatch_admins())}, title, text, source
    )


def notify_admins(title, text, source):
    notify_users(dispatch_admins(), title, text, source)
