from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from common.exceptions import NotFound, ValidationFailure
from missions.models import Mission
from missions.permissions import IsTeamMember
from missions.serializers import StrictInputSerializer, StrictIntegerField
from .models import Notification, MissionSubscription
from . import services


class NotificationSerializer(serializers.ModelSerializer):
    mission_title = serializers.CharField(source='mission.title')
    mission_status = serializers.CharField(source='mission.status')
    detail_url = serializers.SerializerMethodField()

    def get_detail_url(self, obj):
        return f'/missions/{obj.mission_id}'

    class Meta:
        model = Notification
        fields = ['id', 'mission', 'mission_title', 'mission_status', 'detail_url', 'actor', 'kind', 'payload', 'created_at', 'read_at']


class ReadInput(StrictInputSerializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)

    def validate_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError('通知 ID 不得重复。')
        return value


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTeamMember]
    serializer_class = NotificationSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user).select_related('mission')
        mode = self.request.query_params.get('read', 'all')
        if mode not in ('all', 'unread', 'read'):
            raise ValidationFailure('无效的已读筛选。')
        if mode != 'all':
            qs = qs.filter(read_at__isnull=mode == 'unread')
        ordering = self.request.query_params.get('ordering', '-created_at')
        if ordering not in ('created_at', '-created_at'):
            raise ValidationFailure('无效的通知排序。')
        return qs.order_by(ordering, 'id')

    @action(detail=False)
    def summary(self, request):
        return Response({'unread_count': Notification.objects.filter(recipient=request.user, read_at__isnull=True).count()})

    @action(detail=False, methods=['post'])
    def read(self, request):
        data = ReadInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response({'changed_count': services.mark_read(user=request.user, ids=data.validated_data['ids'])})


class SubscriptionInput(StrictInputSerializer):
    mode = serializers.ChoiceField(choices=['Follow', 'Mute'])
    expected_version = StrictIntegerField(min_value=0)


class SubscriptionView(APIView):
    permission_classes = [IsTeamMember]

    def get(self, request, mission_id):
        mission = Mission.objects.filter(pk=mission_id).first()
        if not mission:
            raise NotFound('任务不存在。')
        row = MissionSubscription.objects.filter(user=request.user, mission=mission).first()
        return Response({'subscription': {'id': row.pk, 'mode': row.mode, 'version': row.version} if row else None,
            'effective_following': row.mode == 'Follow' if row else request.user.pk in services.roles(mission),
            'mandatory_reminders': True})

    def put(self, request, mission_id):
        data = SubscriptionInput(data=request.data)
        data.is_valid(raise_exception=True)
        services.set_subscription(user=request.user, mission_id=mission_id, **data.validated_data)
        return self.get(request, mission_id)
