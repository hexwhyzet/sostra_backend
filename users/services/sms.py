import os
import requests
from django.conf import settings


SMSAERO_API_URL = "https://gate.smsaero.ru/v2/sms/send"


def send_sms(phone: str, message: str) -> bool:
    """
    Отправляет SMS сообщение.
    Поддерживает различные SMS-провайдеры через переменные окружения.
    
    Для настройки используйте переменные окружения:
    - SMS_PROVIDER: только 'smsaero'
    - SMS_API_KEY: API ключ провайдера
    """
    provider = os.getenv('SMS_PROVIDER', 'smsaero').lower()
    api_key = os.getenv('SMS_API_KEY', '')
    
    if not api_key:
        print(f"Warning: SMS_API_KEY not set, SMS will not be sent to {phone}")
        return False
    
    try:
        if provider == 'smsaero':
            return _send_sms_smsaero(phone[1:], message, api_key)
        else:
            print(f"Unknown SMS provider: {provider}")
            return False
    except Exception as e:
        print(f"Error sending SMS: {e}")
        return False


def _send_sms_smsaero(
        phone: str,
        message: str,
        api_key: str
) -> bool:
    """
    Отправляет SMS через API SMS Aero.

    Аргументы:
    - phone: номер получателя в формате 7XXXXXXXXXX
    - message: текст SMS
    - api_key: ваш API ключ из кабинета SMS Aero
    - email: email, с которым зарегистрирован API ключ
    - sender: имя отправителя (numeric или текст, если подтверждено)

    Возвращает True если сообщение успешно отправлено.
    """

    email = os.getenv('SMSAERO_EMAIL', '')
    sender = os.getenv('SMSAERO_SENDER', 'SMS Aero')

    payload = {
        "number": phone,
        "text": message,
        "sign": sender,
        "channel": "digital"
    }

    resp = requests.post(
        SMSAERO_API_URL,
        json=payload,
        auth=(email, api_key),
        timeout=15
    )

    try:
        data = resp.json()
    except ValueError:
        print("Sms json response parse error:", resp.text)
        return False

    if data.get("success"):
        return True
    return False