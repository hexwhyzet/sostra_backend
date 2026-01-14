from django.contrib import admin

from myapp.admin_mixins import CustomAdmin
from users.models import Notification, PasswordResetToken


class NotificationAdmin(CustomAdmin):
    readonly_fields = ("created_at",)
    list_display = ("title", "user", "created_at",)


class PasswordResetTokenAdmin(CustomAdmin):
    readonly_fields = ("token", "code", "created_at", "expires_at")
    list_display = ("user", "phone", "created_at", "expires_at", "is_used")
    list_filter = ("is_used", "created_at")
    search_fields = ("user__username", "phone", "token")


def register_user_admin(site):
    site.register(Notification, NotificationAdmin)
    site.register(PasswordResetToken, PasswordResetTokenAdmin)
