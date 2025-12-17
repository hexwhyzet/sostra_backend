from datetime import date, timedelta, datetime

from django.db.models import Q

from dispatch.models import Duty, DutyRole, ExploitationRole, DutyPoint
from dispatch.utils import now
from myproject.settings import AUTH_USER_MODEL


def get_all_duties():
    return Duty.objects.all()


def get_duty_by_id(duty_id):
    return Duty.objects.get(pk=duty_id)


def get_duties_by_date(start_date: date, role: DutyRole = None):
    if role is None:
        return Duty.objects.filter(start_datetime__date=start_date)
    return Duty.objects.filter(start_datetime__date=start_date, role=role)


def get_duties_assigned(start_date: date, duty_role: DutyRole):
    counter = 0
    current_date = start_date
    while counter < 100:
        if not get_duties_by_date(current_date, duty_role).exists():
            break
        counter += 1
        current_date += timedelta(days=1)
    return counter


def get_current_duties(current_datetime, user: AUTH_USER_MODEL = None, role: DutyRole = None, start_offset: int = 15):
    START_OFFSET = timedelta(minutes=start_offset)

    queryset = Duty.objects.filter(start_datetime__lte=current_datetime + START_OFFSET,
                                   end_datetime__gt=current_datetime)
    if user is not None:
        queryset = queryset.filter(user=user)
    if role is not None:
        queryset = queryset.filter(role=role)
    return queryset


def get_related_duty_points(user: AUTH_USER_MODEL = None):
    active_roles = [duty.role for duty in get_current_duties(now(), user)]
    return DutyPoint.objects.filter(
        Q(level_0_role__in=user.exploitation_roles.all()) |
        Q(level_1_role__in=active_roles) |
        Q(level_2_role__in=active_roles) |
        Q(level_3_role__in=active_roles)
    )


def get_duty_point_by_exploitation_role(exploitation_role: ExploitationRole):
    return DutyPoint.objects.filter(level_0_role=exploitation_role)


def get_duty_point_by_duty_role(duty_role: DutyRole):
    return DutyPoint.objects.filter(Q(level_1_role=duty_role) | Q(level_2_role=duty_role) | Q(level_3_role=duty_role)).all()


def get_or_create_duty(duty_date: date, role: DutyRole, defaults):
    defaults['start_datetime'] = datetime(duty_date.year, duty_date.month, duty_date.day, 17, 30, 0)

    next_day = duty_date + timedelta(days=1)
    defaults['end_datetime'] = datetime(next_day.year, next_day.month, next_day.day, 8, 30, 0)
    return Duty.objects.get_or_create(start_datetime__date=duty_date, role=role, defaults=defaults)


def delete_duty(duty_date: date, role: DutyRole):
    Duty.objects.filter(start_datetime__date=duty_date, role=role).delete()
