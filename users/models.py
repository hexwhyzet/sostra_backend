import enum

from django.contrib.auth.models import AbstractUser
from django.db import models

from myproject.settings import AUTH_USER_MODEL


def display_name(user):
    if len(user.first_name) > 0 and len(user.last_name) > 0:
        return user.last_name + ' ' + user.first_name
    elif len(user.first_name) > 0:
        return user.first_name
    elif len(user.last_name) > 0:
        return user.last_name
    return user.username


class User(AbstractUser):
    must_change_password = models.BooleanField(default=False, verbose_name="Необходимо сменить пароль при следующем входе в приложение")
    telegram_user_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name="Telegram ID")

    class Meta:
        db_table = 'auth_user'
        ordering = ['last_name']
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    @property
    def display_name(self):
        return display_name(self)

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.username})"


class NotificationSourceEnum(enum.Enum):
    CANTEEN = "canteen"
    QR_PATROL = "qr_patrol"
    DISPATCH = "dispatch"
    SYSTEM = "system"  # неизвестный источник


class Notification(models.Model):
    SERVICE_CHOICES = [
        (NotificationSourceEnum.CANTEEN.value, "Столовая"),
        (NotificationSourceEnum.QR_PATROL.value, "QR-обход"),
        (NotificationSourceEnum.DISPATCH.value, "Диспетчеризация"),
        (NotificationSourceEnum.SYSTEM.value, "Системное"),
    ]

    user = models.ForeignKey(
        AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.TextField(max_length=255, null=True)
    source = models.CharField(
        max_length=50,
        choices=SERVICE_CHOICES,
        default=NotificationSourceEnum.SYSTEM.value,
        verbose_name="Источник",
    )
    text = models.TextField(max_length=255, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    is_seen = models.BooleanField(default=False, verbose_name="Прочитано ли")

    def __str__(self):
        return f"Уведомление для {self.user}"

    def get_source_display(self):
        """Возвращает человекочитаемое название источника"""
        return dict(self.SERVICE_CHOICES).get(self.source, self.source)
