from django.contrib import admin

from myapp.admin_mixins import CustomAdmin
from users.models import Notification


class NotificationAdmin(CustomAdmin):
    readonly_fields = ("created_at",)
    list_display = ("title", "user", "created_at",)


def register_user_admin(site):
    site.register(Notification, NotificationAdmin)
