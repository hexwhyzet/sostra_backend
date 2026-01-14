import os

from django.core.management import call_command
from pyfcm import FCMNotification

from myapp.models import Device
from myproject.settings import AUTH_USER_MODEL


def telegram_notification(tg_user_id, message):
    """
    Отправить уведомление пользователю через вашу management-команду.
    """
    call_command('sendnotification', str(tg_user_id), message)


def send_fcm_notification(user: AUTH_USER_MODEL, title, body, data=None):
    try:
        fcm = FCMNotification(service_account_file=os.getenv('PATH_TO_GOOGLE_OAUTH_TOKEN'),
                            project_id=os.getenv('FIREBASE_PROJECT_ID'))

        if Device.objects.filter(user=user).exists() and user.device.notification_token is not None:
            result = fcm.notify(
                fcm_token=user.device.notification_token,
                notification_title=title,
                notification_body=body,
                webpush_config={"notification": {"sound": "default"}}
            )
            return result
    except Exception as e:
        print(e)

    if user.telegram_user_id is not None:
        telegram_notification(user.telegram_user_id, title + '\n\n' + body)
