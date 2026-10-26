from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import ValidationFailure
from missions import services
from missions.models import CodeExecution
from . import services as bridge
from .authentication import DeviceAuthentication
from .code_protocol import PATCH_LIMIT, REPORT_LIMIT
from .serializers import StrictSerializer
from .views import parsed


class CodeCreate(StrictSerializer):
    mission_id = serializers.UUIDField()
    device_id = serializers.UUIDField()
    repository_key = serializers.RegexField(r'^[A-Za-z0-9_-]{1,64}$', source='repository_key_value')
    expected_version = serializers.IntegerField(min_value=1)
    instructions = serializers.CharField(max_length=10000)
    idempotency_key = serializers.UUIDField()
    previous_id = serializers.UUIDField(allow_null=True, default=None)


class CodeExecutionSerializer(serializers.ModelSerializer):
    status = serializers.CharField(source='request.status')
    expires_at = serializers.DateTimeField(source='request.expires_at')
    error = serializers.CharField(source='request.error')
    stopped_at = serializers.DateTimeField(source='request.stopped_at')
    patch_url = serializers.SerializerMethodField()
    stale_reason = serializers.SerializerMethodField()

    def get_patch_url(self, obj):
        return obj.patch.url if obj.patch_id else None

    def get_stale_reason(self, obj):
        return bridge.stale_reason(obj.request) if obj.request.status in bridge.ACTIVE else ''

    class Meta:
        model = CodeExecution
        fields = ('id', 'request_id', 'mission_id', 'actor_id', 'mission_version', 'repository_key', 'version',
            'previous_id', 'status', 'manifest', 'report', 'patch_url', 'stale_reason', 'error', 'expires_at',
            'stopped_at', 'created_at', 'published_at')


def executions():
    return CodeExecution.objects.select_related('request', 'actor', 'patch')


class CodeList(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    serializer_class = CodeExecutionSerializer

    def get_queryset(self):
        mission_id = serializers.UUIDField().run_validation(self.request.query_params.get('mission'))
        bridge.expire_requests(bridge.AssistanceRequest.objects.filter(code_execution__mission_id=mission_id))
        return executions().filter(mission_id=mission_id)

    def post(self, request):
        execution = services.create_code_execution(actor=request.user, **parsed(CodeCreate, request))
        return Response(CodeExecutionSerializer(execution).data, status=201)


class CodeDetail(generics.RetrieveAPIView):
    authentication_classes = [SessionAuthentication]
    serializer_class = CodeExecutionSerializer

    def get_queryset(self):
        bridge.expire_requests(bridge.AssistanceRequest.objects.filter(code_execution__pk=self.kwargs['pk']))
        return executions()


class CodeCancel(APIView):
    authentication_classes = [SessionAuthentication]

    def post(self, request, pk):
        services.cancel_code_execution(actor=request.user, execution_id=pk)
        return Response(CodeExecutionSerializer(get_object_or_404(executions(), pk=pk)).data)


class ManifestInput(StrictSerializer):
    attempt_id = serializers.UUIDField()
    manifest = serializers.JSONField()


class PublishInput(StrictSerializer):
    attempt_id = serializers.UUIDField()
    patch = serializers.FileField()
    report = serializers.FileField()


class RunnerCodeManifest(APIView):
    authentication_classes = [DeviceAuthentication]

    def post(self, request, pk):
        result = services.stage_code_execution(device_id=request.auth.pk, request_id=pk, **parsed(ManifestInput, request))
        return Response(CodeExecutionSerializer(result).data)


class RunnerCodePublish(APIView):
    authentication_classes = [DeviceAuthentication]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        if int(request.META.get('CONTENT_LENGTH') or 0) > PATCH_LIMIT + REPORT_LIMIT + 65536:
            raise ValidationFailure('代码成果请求过大。')
        data = PublishInput(data=request.data)
        data.is_valid(raise_exception=True)
        value = data.validated_data
        result = services.publish_code_execution(device_id=request.auth.pk, request_id=pk,
            attempt_id=value['attempt_id'], patch_upload=value['patch'], report_upload=value['report'])
        return Response(CodeExecutionSerializer(result).data)
