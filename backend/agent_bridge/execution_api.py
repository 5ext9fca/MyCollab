from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import ValidationFailure
from library.views import _file_response
from missions import services
from missions.models import MissionExecution, ExecutionCandidate
from . import services as bridge
from .authentication import DeviceAuthentication
from .image_protocol import IMAGE_KINDS, MAX_IMAGE_BYTES
from .serializers import StrictSerializer
from .views import parsed


class ExecutionCreate(StrictSerializer):
    mission_id = serializers.UUIDField()
    asset_id = serializers.UUIDField()
    device_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=IMAGE_KINDS)
    expected_version = serializers.IntegerField(min_value=1)
    asset_version = serializers.IntegerField(min_value=1)
    instructions = serializers.CharField(max_length=10000)
    reference_ids = serializers.ListField(child=serializers.UUIDField(), max_length=4, default=list)
    idempotency_key = serializers.UUIDField()
    previous_id = serializers.UUIDField(allow_null=True, default=None)


class CandidateSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    def get_url(self, obj):
        return obj.file.url if obj.file_id else None

    class Meta:
        model = ExecutionCandidate
        fields = ('id', 'key', 'name', 'sha256', 'size', 'width', 'height', 'file_id', 'url', 'uploaded_at')


class ExecutionSerializer(serializers.ModelSerializer):
    status = serializers.CharField(source='request.status')
    kind = serializers.CharField(source='request.kind')
    expires_at = serializers.DateTimeField(source='request.expires_at')
    error = serializers.CharField(source='request.error')
    stopped_at = serializers.DateTimeField(source='request.stopped_at')
    candidates = CandidateSerializer(many=True)
    stale_reason = serializers.SerializerMethodField()

    def get_stale_reason(self, obj):
        if obj.request.status in bridge.ACTIVE:
            return bridge.stale_reason(obj.request)
        return ''

    class Meta:
        model = MissionExecution
        fields = ('id', 'request_id', 'mission_id', 'asset_id', 'actor_id', 'mission_version', 'asset_version',
            'version', 'previous_id', 'kind', 'status', 'selected_ids', 'candidates', 'stale_reason', 'expires_at', 'error', 'stopped_at', 'created_at')


def executions():
    return MissionExecution.objects.select_related('request', 'actor').prefetch_related('candidates__file')


class ExecutionList(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    serializer_class = ExecutionSerializer

    def get_queryset(self):
        serializer = serializers.UUIDField()
        mission_id = serializer.run_validation(self.request.query_params.get('mission'))
        query = executions().filter(mission_id=mission_id)
        bridge.expire_requests(bridge.AssistanceRequest.objects.filter(execution__mission_id=mission_id))
        return query

    def post(self, request):
        execution = services.create_execution(actor=request.user, **parsed(ExecutionCreate, request))
        return Response(ExecutionSerializer(execution).data, status=201)


class ExecutionDetail(generics.RetrieveAPIView):
    authentication_classes = [SessionAuthentication]
    serializer_class = ExecutionSerializer

    def get_queryset(self):
        bridge.expire_requests(bridge.AssistanceRequest.objects.filter(execution__pk=self.kwargs['pk']))
        return executions()


class ExecutionCancel(APIView):
    authentication_classes = [SessionAuthentication]

    def post(self, request, pk):
        services.cancel_execution(actor=request.user, execution_id=pk)
        return Response(ExecutionSerializer(get_object_or_404(executions(), pk=pk)).data)


class ManifestInput(StrictSerializer):
    attempt_id = serializers.UUIDField()
    manifest = serializers.JSONField()


class SelectionInput(StrictSerializer):
    attempt_id = serializers.UUIDField()
    keys = serializers.ListField(child=serializers.RegexField(r'^[A-Za-z0-9_-]{1,50}$'), min_length=1, max_length=4)


class AttemptInput(StrictSerializer):
    attempt_id = serializers.UUIDField()


class UploadInput(AttemptInput):
    file = serializers.FileField()


class RunnerExecution(APIView):
    authentication_classes = [DeviceAuthentication]


class RunnerManifest(RunnerExecution):
    def post(self, request, pk):
        execution = services.publish_execution_candidates(device_id=request.auth.pk, request_id=pk, **parsed(ManifestInput, request))
        return Response(ExecutionSerializer(execution).data)


class RunnerSelection(RunnerExecution):
    def post(self, request, pk):
        execution = services.select_execution_candidates(device_id=request.auth.pk, request_id=pk, **parsed(SelectionInput, request))
        return Response(ExecutionSerializer(execution).data)


class RunnerUpload(RunnerExecution):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk, key):
        if int(request.META.get('CONTENT_LENGTH') or 0) > MAX_IMAGE_BYTES + 65536:
            raise ValidationFailure('上传请求过大。')
        data = UploadInput(data=request.data)
        data.is_valid(raise_exception=True)
        candidate = services.upload_execution_candidate(device_id=request.auth.pk, request_id=pk,
            attempt_id=data.validated_data['attempt_id'], key=key, upload=data.validated_data['file'])
        return Response(CandidateSerializer(candidate).data)


class RunnerComplete(RunnerExecution):
    def post(self, request, pk):
        execution = services.complete_execution(device_id=request.auth.pk, request_id=pk, **parsed(AttemptInput, request))
        return Response(ExecutionSerializer(execution).data)


class RunnerReference(RunnerExecution):
    def post(self, request, pk, file_id):
        record = services.execution_reference(device_id=request.auth.pk, request_id=pk, file_id=file_id, **parsed(AttemptInput, request))
        return _file_response(record)
