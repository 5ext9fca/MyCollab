"""保存视图的严格定义校验、私有可见性和日期解析。"""
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from accounts.models import User
from common.exceptions import NotFound, PermissionDenied, ValidationFailure
from .models import SavedMissionView, Mission, Milestone, DesignElement, ProductionBatch, MissionStatus, MissionType, MissionPriority
from .filters import ORDERING_FIELDS, parse_uuid
from .scheduling import date_window
from .services import _acquire_team_lock, _check_version
from .serializers import StrictInputSerializer, StrictIntegerField
from .permissions import IsTeamMember

FILTERS = {'q', 'status', 'type', 'priority', 'tag', 'creator', 'assignee', 'reviewer', 'parent', 'milestone', 'design_element', 'production_batch', 'blocked', 'revalidation'}


def invalid(field, message):
    raise ValidationFailure(message, field_errors={field: [message]})


def validate_definition(definition, target):
    if not isinstance(definition, dict) or set(definition) != {'filters', 'ordering', 'date_window', 'zoom'}:
        invalid('definition', '定义必须包含 filters、ordering、date_window、zoom 且不能有其他字段。')
    filters = definition['filters']
    if not isinstance(filters, dict) or set(filters) - FILTERS:
        invalid('filters', '包含未知筛选字段。')
    normalized = {}
    for key, value in filters.items():
        if key == 'tag':
            if not isinstance(value, list) or any(not isinstance(t, str) or not t.strip() or len(t.strip()) > 50 for t in value):
                invalid(key, '标签必须是非空字符串数组，每项至多 50 字符。')
            normalized[key] = list(dict.fromkeys(t.strip() for t in value))
            continue
        if key in ('blocked', 'revalidation'):
            if type(value) is not bool:
                invalid(key, '须为布尔值。')
            normalized[key] = value
            continue
        if key in ('creator', 'assignee', 'reviewer'):
            if value not in ('me', 'none'):
                if type(value) is not int or value < 1 or not User.objects.filter(pk=value).exists():
                    invalid(key, '成员必须是存在的整数 ID、me 或 none。')
            normalized[key] = value
            continue
        if not isinstance(value, str) or not value.strip():
            invalid(key, '须为非空字符串。')
        value = value.strip()
        enums = {'status': MissionStatus.values, 'type': MissionType.values, 'priority': MissionPriority.values}
        if key in enums and value not in enums[key]:
            invalid(key, '未知枚举值。')
        refs = {'parent': (Mission, {'root'}), 'milestone': (Milestone, {'none'}), 'design_element': (DesignElement, {'none'}), 'production_batch': (ProductionBatch, {'none'})}
        if key in refs:
            model, special = refs[key]
            if value not in special:
                value = str(parse_uuid(value, key))
                if not model.objects.filter(pk=value).exists():
                    invalid(key, '引用对象不存在，请修复筛选；不会移除条件扩大查询。')
        normalized[key] = value
    ordering = definition['ordering']
    if ordering is not None and (not isinstance(ordering, str) or ordering not in ORDERING_FIELDS | {'-' + k for k in ORDERING_FIELDS}):
        invalid('ordering', '排序字段无效。')
    zoom = definition['zoom']
    if zoom is not None and (target != 'Gantt' or zoom not in ('day', 'week')):
        invalid('zoom', '只有甘特视图可设置 day/week 缩放。')
    window = definition['date_window']
    if window is not None:
        if not isinstance(window, dict):
            invalid('date_window', '计划窗口格式错误。')
        if window.get('mode') == 'absolute' and set(window) == {'mode', 'date_from', 'date_to'}:
            date_window(window)
        elif window.get('mode') == 'relative' and set(window) == {'mode', 'preset'} and window['preset'] in ('this_week', 'next_7_days'):
            pass
        else:
            invalid('date_window', '计划窗口格式或相对日期选项无效。')
    return {'filters': normalized, 'ordering': ordering, 'date_window': window, 'zoom': zoom}


def visible(user):
    return SavedMissionView.objects.filter(Q(owner=user) | Q(visibility='Team'))


def resolve(row, user):
    definition = validate_definition(row.definition, row.target)
    today = timezone.localdate()
    query = {}
    for key, value in definition['filters'].items():
        if key in ('creator', 'assignee', 'reviewer') and value == 'me':
            value = user.pk
        query[key] = str(value).lower() if type(value) is bool else value
    if definition['ordering']:
        query['ordering'] = definition['ordering']
    window = definition['date_window']
    if window:
        if window['mode'] == 'absolute':
            query.update(date_from=window['date_from'], date_to=window['date_to'])
        else:
            start = today - timedelta(days=today.weekday()) if window['preset'] == 'this_week' else today
            query.update(date_from=start.isoformat(), date_to=(start + timedelta(days=6)).isoformat())
    if definition['zoom']:
        query['zoom'] = definition['zoom']
    return {'target': row.target, 'query': query, 'today': today, 'warnings': []}


@transaction.atomic
def save_view(*, actor, data, view_id=None):
    _acquire_team_lock()
    if view_id:
        row = visible(actor).select_for_update().filter(pk=view_id).first()
        if not row:
            raise NotFound('视图不存在。')
        if row.owner_id != actor.pk and not (row.visibility == 'Team' and actor.is_staff):
            raise PermissionDenied('只有作者或管理员可修改团队视图。')
        _check_version(row, data['expected_version'])
    else:
        row = SavedMissionView(owner=actor)
    for field in ('name', 'visibility', 'target', 'definition'):
        if field in data:
            setattr(row, field, data[field])
    row.name = row.name.strip()
    if not 1 <= len(row.name) <= 100:
        invalid('name', '名称须为 1–100 字符。')
    row.definition = validate_definition(row.definition, row.target)
    if SavedMissionView.objects.filter(owner=row.owner, name=row.name).exclude(pk=row.pk).exists():
        invalid('name', '你已保存同名视图。')
    if view_id:
        row.version += 1
    row.save()
    return row


@transaction.atomic
def delete_view(*, actor, view_id, expected_version):
    _acquire_team_lock()
    row = visible(actor).select_for_update().filter(pk=view_id).first()
    if not row:
        raise NotFound('视图不存在。')
    if row.owner_id != actor.pk and not (row.visibility == 'Team' and actor.is_staff):
        raise PermissionDenied('只有作者或管理员可删除团队视图。')
    _check_version(row, expected_version)
    row.delete()


class SavedViewInput(StrictInputSerializer):
    name = serializers.CharField(max_length=100)
    visibility = serializers.ChoiceField(choices=['Private', 'Team'], default='Private')
    target = serializers.ChoiceField(choices=['List', 'Overview', 'Gantt'])
    definition = serializers.JSONField()
    expected_version = StrictIntegerField(min_value=1, required=False)


class SavedViewSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.username')
    warnings = serializers.SerializerMethodField()

    def get_warnings(self, obj):
        try:
            validate_definition(obj.definition, obj.target)
            return []
        except ValidationFailure as exc:
            return [exc.message]

    class Meta:
        model = SavedMissionView
        fields = ['id', 'name', 'owner', 'owner_name', 'visibility', 'target', 'definition', 'version', 'created_at', 'updated_at', 'warnings']


class SavedViewSet(viewsets.GenericViewSet):
    permission_classes = [IsTeamMember]
    serializer_class = SavedViewSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = visible(self.request.user).select_related('owner')
        visibility = self.request.query_params.get('visibility')
        if visibility:
            if visibility not in ('Private', 'Team'):
                invalid('visibility', '无效的可见范围。')
            qs = qs.filter(visibility=visibility)
        return qs

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    def create(self, request):
        data = SavedViewInput(data=request.data); data.is_valid(raise_exception=True)
        if 'expected_version' in data.validated_data:
            invalid('expected_version', '创建视图无需版本。')
        return Response(self.get_serializer(save_view(actor=request.user, data=data.validated_data)).data, status=201)

    def partial_update(self, request, pk=None):
        self.get_object()
        data = SavedViewInput(data=request.data, partial=True); data.is_valid(raise_exception=True)
        if 'expected_version' not in data.validated_data:
            invalid('expected_version', '版本必填。')
        return Response(self.get_serializer(save_view(actor=request.user, data=data.validated_data, view_id=pk)).data)

    def destroy(self, request, pk=None):
        self.get_object()
        value = request.query_params.get('expected_version', '')
        if not value.isdecimal() or int(value) < 1:
            invalid('expected_version', '版本须为正整数。')
        delete_view(actor=request.user, view_id=pk, expected_version=int(value))
        return Response(status=204)

    @action(detail=True)
    def resolve(self, request, pk=None):
        return Response(resolve(self.get_object(), request.user))
