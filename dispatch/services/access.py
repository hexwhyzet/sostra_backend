from django.contrib.auth import get_user_model

from dispatch.models import Duty, DutyPoint
from myapp.admin import user_has_group
from myapp.custom_groups import DispatchAdminManager
from myproject.settings import AUTH_USER_MODEL


def has_access_to_dispatch(user: AUTH_USER_MODEL):
    if Duty.objects.filter(user=user).exists():
        # Хотя бы раз он был или будет дежурным
        return True

    if user.admin_duty_points.exists():
        # Если он админ какой-то точки
        return True

    if user.exploitation_roles.exists():
        # Если он участник какой-то роли эксплуатации
        return True

    return False


def dispatch_admins():
    return get_user_model().objects.filter(groups__name__in=[DispatchAdminManager.name]).all()


def has_dispatch_admin_rights(user: AUTH_USER_MODEL, point: DutyPoint = None):
    return user_has_group(user, DispatchAdminManager) or (point is not None and point.admins.contains(user))
