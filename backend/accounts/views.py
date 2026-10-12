from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import mixins, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import RegistrationRequest, User
from .serializers import (
    LoginSerializer,
    MeSerializer,
    MemberSerializer,
    RegisterSerializer,
    RegistrationRequestSerializer,
    RejectSerializer,
    UserBriefSerializer,
)


def enforce_csrf(request):
    """Run DRF's CSRF validation for unauthenticated writes.

    DRF APIViews are ``csrf_exempt`` by default and only validate CSRF through
    ``SessionAuthentication`` when a user is already logged in. The login and
    registration endpoints therefore have to enforce it explicitly.
    """
    SessionAuthentication().enforce_csrf(request)


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """Set the CSRF cookie so the SPA can send unsafe requests."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"detail": "CSRF cookie set."})


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        enforce_csrf(request)
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {
                    "code": "invalid_credentials",
                    "message": "用户名或密码错误。",
                    "field_errors": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        login(request, user)
        return Response(MeSerializer(user).data)


class RegisterView(APIView):
    """Public self-service registration; creates a pending request only."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        enforce_csrf(request)
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        registration = services.submit_registration(
            username=data["username"],
            password=data["password"],
            email=data.get("email", ""),
            display_name=data.get("display_name", ""),
            message=data.get("message", ""),
        )
        return Response(
            RegistrationRequestSerializer(registration).data,
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class MemberListView(ListAPIView):
    """Active team members, used by the SPA to pick a reviewer.

    Read-only and visible to every authenticated member (unlike the admin
    ``/api/admin/users`` list); only id / username / display_name are exposed.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = UserBriefSerializer
    pagination_class = None

    def get_queryset(self):
        return User.objects.filter(is_active=True).order_by("username")


class AdminRegistrationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Admin console: review self-service registration requests."""

    permission_classes = [IsAdminUser]
    serializer_class = RegistrationRequestSerializer
    http_method_names = ["get", "post", "head", "options"]
    lookup_value_regex = "[0-9a-fA-F-]{36}"

    def get_queryset(self):
        qs = RegistrationRequest.objects.select_related("reviewed_by")
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        registration = services.approve_registration(actor=request.user, request_id=pk)
        return Response(RegistrationRequestSerializer(registration).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        registration = services.reject_registration(
            actor=request.user,
            request_id=pk,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(RegistrationRequestSerializer(registration).data)


class AdminUserListView(ListAPIView):
    """Admin console: read-only member list."""

    permission_classes = [IsAdminUser]
    serializer_class = MemberSerializer

    def get_queryset(self):
        qs = User.objects.order_by("-date_joined", "username")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
            )
        return qs
