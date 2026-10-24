"""只读日期窗口：分页列表与时间视图采用相同的区间语义。"""
from datetime import date, timedelta
from django.db.models import Q
from django.utils import timezone
from .exceptions import ValidationFailure


def date_window(params, *, default=False):
    supplied = 'date_from' in params or 'date_to' in params
    if not supplied:
        if not default:
            return None
        today = timezone.localdate()
        return today - timedelta(days=14), today + timedelta(days=42)
    try:
        start, end = date.fromisoformat(params['date_from']), date.fromisoformat(params['date_to'])
        if start.isoformat() != params['date_from'] or end.isoformat() != params['date_to']:
            raise ValueError
        if not 0 <= (end - start).days <= 365:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValidationFailure('日期范围须同时提供 YYYY-MM-DD 起止日期，且为 1–366 个自然日。', field_errors={'date_from': ['日期范围无效。']})
    return start, end


def filter_schedule(qs, start, end):
    return qs.filter(
        Q(planned_start_date__lte=end, planned_end_date__gte=start)
        | Q(planned_start_date__range=(start, end), planned_end_date__isnull=True)
        | Q(planned_start_date__isnull=True, planned_end_date__range=(start, end))
        | Q(planned_start_date__isnull=True, planned_end_date__isnull=True)
    )
