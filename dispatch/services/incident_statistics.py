from datetime import date, datetime
from django.db.models import Q, Count, Avg
from django.utils import timezone
from typing import Optional, Dict, List

from dispatch.models import Incident, DutyPoint
from myproject.settings import AUTH_USER_MODEL


def get_incident_statistics(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    responsible_user_id: Optional[int] = None,
    point_id: Optional[int] = None,
    author_id: Optional[int] = None,
) -> Dict:
    """
    Получает статистику по инцидентам с фильтрами
    
    Args:
        start_date: Дата начала периода
        end_date: Дата окончания периода
        status: Статус инцидента
        responsible_user_id: ID ответственного дежурного
        point_id: ID системы дежурства
        author_id: ID автора инцидента
    
    Returns:
        Словарь со статистикой и списком инцидентов
    """
    queryset = Incident.objects.all()
    
    # Фильтр по дате
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)
    
    # Фильтр по статусу
    if status:
        queryset = queryset.filter(status=status)
    
    # Фильтр по ответственному дежурному
    if responsible_user_id:
        queryset = queryset.filter(responsible_user_id=responsible_user_id)
    
    # Фильтр по системе дежурства
    if point_id:
        queryset = queryset.filter(point_id=point_id)
    
    # Фильтр по автору
    if author_id:
        queryset = queryset.filter(author_id=author_id)
    
    # Получаем список инцидентов
    incidents = queryset.select_related('author', 'responsible_user', 'point').order_by('-created_at')
    
    # Вычисляем метрики
    total_count = incidents.count()
    
    # Статистика по статусам
    status_stats = {}
    for status_choice in Incident.STATUS_CHOICES:
        status_value = status_choice[0]
        count = incidents.filter(status=status_value).count()
        status_stats[status_value] = {
            'count': count,
            'display': status_choice[1],
            'percentage': round((count / total_count * 100) if total_count > 0 else 0, 2)
        }
    
    # Статистика по уровням
    level_stats = {}
    for level in range(5):  # Уровни от 0 до 4
        count = incidents.filter(level=level).count()
        if count > 0:
            level_stats[level] = {
                'count': count,
                'percentage': round((count / total_count * 100) if total_count > 0 else 0, 2)
            }
    
    # Статистика по критичности
    critical_count = incidents.filter(is_critical=True).count()
    non_critical_count = total_count - critical_count
    
    # Средний уровень эскалации
    avg_level = incidents.aggregate(avg_level=Avg('level'))['avg_level'] or 0
    
    # Статистика по системам дежурства
    point_stats = {}
    point_counts = incidents.values('point__name', 'point__id').annotate(
        count=Count('id')
    ).order_by('-count')
    
    for item in point_counts:
        if item['point__name']:
            point_stats[item['point__id']] = {
                'name': item['point__name'],
                'count': item['count'],
                'percentage': round((item['count'] / total_count * 100) if total_count > 0 else 0, 2)
            }
    
    # Статистика по ответственным дежурным
    responsible_stats = {}
    responsible_counts = incidents.filter(responsible_user__isnull=False).values(
        'responsible_user__id', 'responsible_user__first_name', 'responsible_user__last_name', 'responsible_user__username'
    ).annotate(count=Count('id')).order_by('-count')
    
    from users.models import display_name
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    for item in responsible_counts:
        user_id = item['responsible_user__id']
        try:
            user = User.objects.get(pk=user_id)
            user_display_name = user.display_name
        except User.DoesNotExist:
            user_display_name = item.get('responsible_user__username', 'Неизвестно')
        
        responsible_stats[user_id] = {
            'name': user_display_name,
            'count': item['count'],
            'percentage': round((item['count'] / total_count * 100) if total_count > 0 else 0, 2)
        }
    
    return {
        'total_count': total_count,
        'status_statistics': status_stats,
        'level_statistics': level_stats,
        'critical_statistics': {
            'critical': {
                'count': critical_count,
                'percentage': round((critical_count / total_count * 100) if total_count > 0 else 0, 2)
            },
            'non_critical': {
                'count': non_critical_count,
                'percentage': round((non_critical_count / total_count * 100) if total_count > 0 else 0, 2)
            }
        },
        'average_level': round(avg_level, 2),
        'point_statistics': point_stats,
        'responsible_statistics': responsible_stats,
        'incidents': [
            {
                'id': incident.id,
                'name': incident.name,
                'description': incident.description,
                'status': incident.status,
                'level': incident.level,
                'is_critical': incident.is_critical,
                'created_at': incident.created_at.isoformat(),
                'author__id': incident.author.id if incident.author else None,
                'author__display_name': incident.author.display_name if incident.author else None,
                'responsible_user__id': incident.responsible_user.id if incident.responsible_user else None,
                'responsible_user__display_name': incident.responsible_user.display_name if incident.responsible_user else None,
                'point__id': incident.point.id if incident.point else None,
                'point__name': incident.point.name if incident.point else None,
            }
            for incident in incidents
        ]
    }

