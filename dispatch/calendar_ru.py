"""
Нерабочие дни по производственному календарю России.
Используется для создания дежурств на выходные и праздники.
"""
from datetime import date, timedelta

from workalendar.europe import Russia


def get_non_working_ranges(start_date: date, end_date: date) -> list[tuple[date, date]]:
    """
    Возвращает список непрерывных периодов нерабочих дней в заданном диапазоне.
    Каждый элемент — (дата начала, дата окончания) включительно.
    """
    cal = Russia()
    non_working = []
    current = start_date
    while current <= end_date:
        if not cal.is_working_day(current):
            non_working.append(current)
        current += timedelta(days=1)

    if not non_working:
        return []

    ranges = []
    range_start = non_working[0]
    range_end = non_working[0]
    for d in non_working[1:]:
        if d == range_end + timedelta(days=1):
            range_end = d
        else:
            ranges.append((range_start, range_end))
            range_start = d
            range_end = d
    ranges.append((range_start, range_end))
    return ranges
