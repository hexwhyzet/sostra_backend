import enum
import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

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
    phone = models.CharField(max_length=20, null=True, blank=True, verbose_name="Номер телефона", help_text="Формат: +7XXXXXXXXXX")

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
    duty_action = models.ForeignKey(
        "dispatch.DutyAction",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name="Действие с дежурством",
    )

    def __str__(self):
        return f"Уведомление для {self.user}"

    def get_source_display(self):
        """Возвращает человекочитаемое название источника"""
        return dict(self.SERVICE_CHOICES).get(self.source, self.source)


class PasswordResetToken(models.Model):
    """Модель для хранения токенов восстановления пароля"""
    user = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='Пользователь')
    token = models.CharField(max_length=64, unique=True, verbose_name='Токен')
    code = models.CharField(max_length=6, verbose_name='Код подтверждения')
    phone = models.CharField(max_length=20, verbose_name='Номер телефона')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Время создания')
    expires_at = models.DateTimeField(verbose_name='Время истечения')
    is_used = models.BooleanField(default=False, verbose_name='Использован ли')

    class Meta:
        verbose_name = "Токен восстановления пароля"
        verbose_name_plural = "Токены восстановления пароля"
        ordering = ['-created_at']

    def __str__(self):
        return f"Token for {self.user.username} - {self.phone}"

    @classmethod
    def create_token(cls, user, phone):
        """Создает новый токен восстановления пароля"""
        # Удаляем старые неиспользованные токены для этого пользователя
        cls.objects.filter(user=user, is_used=False, expires_at__gt=timezone.now()).delete()
        
        token = secrets.token_urlsafe(32)
        code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        expires_at = timezone.now() + timedelta(minutes=15)
        
        return cls.objects.create(
            user=user,
            token=token,
            code=code,
            phone=phone,
            expires_at=expires_at
        )

    def is_valid(self):
        """Проверяет, действителен ли токен"""
        return not self.is_used and timezone.now() < self.expires_at

    def mark_as_used(self):
        """Помечает токен как использованный"""
        self.is_used = True
        self.save()
