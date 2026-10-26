from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from rest_framework.views import APIView

from common.permissions import IsTeamMember
from missions import services


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["请求包含未知字段。"]})
        return super().to_internal_value(data)


class CreateInput(StrictSerializer):
    name = serializers.CharField(max_length=255)
    size = serializers.IntegerField(min_value=0, max_value=100 * 1024 * 1024)
    sha256 = serializers.RegexField(r"^[a-f0-9]{64}$")
    token = serializers.RegexField(r"^[a-f0-9]{64}$")


class JoinInput(StrictSerializer):
    code = serializers.RegexField(r"^[A-Fa-f0-9]{12}$")
    token = serializers.RegexField(r"^[a-f0-9]{64}$")


class OperationInput(StrictSerializer):
    token = serializers.RegexField(r"^[a-f0-9]{64}$")
    action = serializers.ChoiceField(choices=["poll", "accept", "offer", "answer", "complete", "cancel", "fail"], default="poll")
    sdp = serializers.CharField(max_length=16384, required=False, trim_whitespace=False)
    sha256 = serializers.RegexField(r"^[a-f0-9]{64}$", required=False)
    error = serializers.CharField(max_length=40, required=False)


class TransferView(APIView):
    permission_classes = [IsTeamMember]
    parser_classes = [JSONParser]

    def respond(self, serializer_type, operation, request, **kwargs):
        serializer = serializer_type(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = Response(operation(actor=request.user, **kwargs, **serializer.validated_data))
        response["Cache-Control"] = "no-store"
        return response


class CreateView(TransferView):
    def post(self, request):
        return self.respond(CreateInput, services.create_file_transfer, request)


class JoinView(TransferView):
    def post(self, request):
        return self.respond(JoinInput, services.join_file_transfer, request)


class OperationView(TransferView):
    def post(self, request, transfer_id):
        return self.respond(OperationInput, services.operate_file_transfer, request, transfer_id=transfer_id)
