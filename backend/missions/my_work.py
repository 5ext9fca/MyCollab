"""个人待办实时读模型，分类共享同一天与同一查询口径。"""
from datetime import timedelta
from django.db.models import Exists, OuterRef, Q, F
from django.utils import timezone
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from notifications.models import Notification
from .models import Mission, MissionDependency
from .filters import apply_mission_filters, OPEN_STATUSES, _unresolved_prerequisites_for_outer
from .exceptions import ValidationFailure
from .permissions import IsTeamMember
from .serializers import MissionListSerializer

CATEGORIES = ('review', 'returned', 'due_soon', 'overdue', 'unblocked', 'revalidation')


def work_query(user, category, today):
    qs = Mission.objects.select_related('creator', 'assignee', 'reviewer', 'milestone', 'design_element', 'parent').prefetch_related('tags', 'assets')
    related = Q(creator=user) | Q(assignee=user) | Q(reviewer=user)
    if category == 'review':
        qs = qs.filter(reviewer=user, status='Submitted')
    elif category == 'returned':
        qs = qs.filter(assignee=user, status='InProgress', current_submission__outcome='Rejected')
    elif category in ('due_soon', 'overdue'):
        qs = qs.filter(related, status__in=OPEN_STATUSES)
        qs = qs.filter(planned_end_date__lt=today) if category == 'overdue' else qs.filter(planned_end_date__range=(today, today + timedelta(days=3)))
    elif category == 'unblocked':
        qs = qs.annotate(_unresolved=Exists(_unresolved_prerequisites_for_outer()),
            _has_dependencies=Exists(MissionDependency.objects.filter(mission=OuterRef('pk'))))
        qs = qs.filter(assignee=user, status='InProgress', _unresolved=False, _has_dependencies=True)
    elif category == 'revalidation':
        qs = qs.annotate(_unresolved=Exists(_unresolved_prerequisites_for_outer())).filter(
            Q(creator=user) | Q(reviewer=user), status='Done', _unresolved=True)
    else:
        raise ValidationFailure('请选择有效的待办分类。', field_errors={'category': ['分类必填且须为已知分类。']})
    return qs.order_by(F('planned_end_date').asc(nulls_last=True), '-updated_at', 'id')


class MyWorkSummary(APIView):
    permission_classes = [IsTeamMember]

    def get(self, request):
        today = timezone.localdate()
        return Response({'today': today, 'counts': {key: work_query(request.user, key, today).count() for key in CATEGORIES},
            'unread_notification_count': Notification.objects.filter(recipient=request.user, read_at__isnull=True).count()})


class MyWorkMissions(ListAPIView):
    permission_classes = [IsTeamMember]
    serializer_class = MissionListSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'today': self.today}

    def get_queryset(self):
        self.today = timezone.localdate()
        if set(self.request.query_params) - {'category', 'page', 'page_size', 'q', 'ordering', 'status', 'type', 'priority', 'milestone', 'tag', 'blocked', 'design_element'}:
            raise ValidationFailure('个人工作列表不支持额外筛选。')
        return apply_mission_filters(work_query(self.request.user, self.request.query_params.get('category'), self.today), self.request.query_params, user=self.request.user)
