from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import ValidationFailure
from .authentication import DeviceAuthentication
from .models import AgentDevice, AssistanceRequest
from .serializers import (DeviceSerializer, DeviceCreateSerializer, RequestSerializer,
    RequestCreateSerializer, RequestSummarySerializer, HeartbeatSerializer, ResultSerializer)
from . import services, protocol


def parsed(serializer_class, request):
    # 在解析之前拒绝超大 JSON，避免把供应商原始响应持久化。
    if len(request.body) > 270 * 1024:
        raise ValidationFailure("请求体过大。")
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class DeviceList(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    serializer_class = DeviceSerializer

    def get_queryset(self):
        return AgentDevice.objects.filter(owner=self.request.user)

    def post(self, request):
        device, token = services.create_device(request.user, **parsed(DeviceCreateSerializer, request))
        response = Response({**DeviceSerializer(device).data, "token": token}, status=status.HTTP_201_CREATED)
        response["Cache-Control"] = "no-store"
        return response


class DeviceRevoke(APIView):
    authentication_classes = [SessionAuthentication]

    def post(self, request, pk):
        return Response(DeviceSerializer(services.revoke_device(request.user, pk)).data)


class RequestList(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    serializer_class = RequestSummarySerializer

    def get_queryset(self):
        queryset = AssistanceRequest.objects.filter(owner=self.request.user, kind__in=protocol.KINDS).select_related("owner")
        services.expire_requests(queryset)
        return queryset

    def post(self, request):
        payload = parsed(RequestCreateSerializer, request)
        if payload["kind"] == "agent_requirements":
            from missions.services import create_agent_requirements
            item = create_agent_requirements(request.user, **payload)
        else:
            item = services.create_request(request.user, **payload)
        return Response(RequestSerializer(item).data, status=status.HTTP_201_CREATED)


class RequestDetail(generics.RetrieveAPIView):
    authentication_classes = [SessionAuthentication]
    serializer_class = RequestSerializer

    def get_queryset(self):
        queryset = AssistanceRequest.objects.filter(owner=self.request.user, kind__in=protocol.KINDS).select_related("owner")
        services.expire_requests(queryset)
        return queryset


class RequestCancel(APIView):
    authentication_classes = [SessionAuthentication]

    def post(self, request, pk):
        return Response(RequestSerializer(services.cancel(request.user, pk)).data)


class RunnerView(APIView):
    authentication_classes = [DeviceAuthentication]


class RunnerClaim(RunnerView):
    def post(self, request):
        item = services.claim(request.auth.pk)
        return Response(RequestSerializer(item).data if item else None)


class RunnerHeartbeat(RunnerView):
    def post(self, request, pk):
        item = services.heartbeat(request.auth.pk, pk, **parsed(HeartbeatSerializer, request))
        return Response({"status": item.status, "stopped_at": item.stopped_at, "lease_expires_at": item.lease_expires_at})


class RunnerResult(RunnerView):
    def post(self, request, pk):
        item = services.finish(request.auth.pk, pk, **parsed(ResultSerializer, request))
        return Response({"id": str(item.pk), "status": item.status})


class RunnerStatus(RunnerView):
    def post(self, request):
        # 只读探测不领取任务，不扩大设备令牌权限。
        return Response({"schema_versions": [1], "capabilities": request.auth.capabilities,
                         "expires_at": request.auth.expires_at, "lease_seconds": 180})
