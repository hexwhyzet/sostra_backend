import os
import requests
from django.conf import settings


def send_sms(phone: str, message: str) -> bool:
    """
    Отправляет SMS сообщение.
    Поддерживает различные SMS-провайдеры через переменные окружения.
    
    Для настройки используйте переменные окружения:
    - SMS_PROVIDER: только 'smsru'
    - SMS_API_KEY: API ключ провайдера
    """
    provider = os.getenv('SMS_PROVIDER', 'smsru').lower()
    api_key = os.getenv('SMS_API_KEY', '')
    
    if not api_key:
        print(f"Warning: SMS_API_KEY not set, SMS will not be sent to {phone}")
        return False
    
    try:
        if provider == 'smsru':
            return _send_sms_smsru(phone, message, api_key)
        else:
            print(f"Unknown SMS provider: {provider}")
            return False
    except Exception as e:
        print(f"Error sending SMS: {e}")
        return False


def _send_sms_smsru(phone: str, message: str, api_key: str) -> bool:
    """Отправка SMS через sms.ru"""
    url = "https://sms.ru/sms/send"
    params = {
        'api_id': api_key,
        'to': phone[1:],
        'msg': message,
        'json': 1
    }
    response = requests.get(url, params=params, timeout=10)
    result = response.json()
    return result.get('status') == 'OK'
