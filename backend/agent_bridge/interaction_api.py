"""会话数据按发起人隔离；不继承团队可读成果的权限。"""
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from missions import services
from .serializers import StrictSerializer
from .views import RunnerView, parsed


class Binding(StrictSerializer):
    attempt_id = serializers.UUIDField()
    session_nonce = serializers.UUIDField()


class OpenInput(Binding):
    supports_followup = serializers.BooleanField()
    supports_permissions = serializers.BooleanField()


class Acknowledgement(StrictSerializer):
    command_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=['applied', 'rejected'])


class ExchangeInput(Binding):
    events = serializers.ListField(child=serializers.JSONField(), max_length=20, default=list)
    acknowledgements = Acknowledgement(many=True, max_length=100, default=list)
    close = serializers.BooleanField(default=False)


class CommandInput(Binding):
    command_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=['followup', 'permission_reply'])
    payload = serializers.JSONField()


class StateQuery(StrictSerializer):
    after = serializers.IntegerField(min_value=0, max_value=1000, default=0)


class InteractionState(APIView):
    authentication_classes = [SessionAuthentication]

    def get(self, request, pk):
        query = StateQuery(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        response = Response(services.interaction_state(request.user, pk, **query.validated_data))
        response['Cache-Control'] = 'no-store'
        return response

    def post(self, request, pk):
        return Response(services.create_interaction_command(request.user, pk, **parsed(CommandInput, request)), status=201)


class RunnerInteractionOpen(RunnerView):
    def post(self, request, pk):
        return Response(services.open_interaction(request.auth.pk, pk, **parsed(OpenInput, request)))


class RunnerInteractionExchange(RunnerView):
    def post(self, request, pk):
        return Response(services.exchange_interaction(request.auth.pk, pk, **parsed(ExchangeInput, request)))
