from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import AgentDevice
from .services import digest


class DeviceAuthentication(BaseAuthentication):
    """仅挂载在 Runner 端点，绝不回退到浏览器会话。"""

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if len(parts) != 2 or parts[0].lower() != b"bearer":
            raise AuthenticationFailed("请提供本地设备凭据。")
        try:
            token = parts[1].decode("ascii")
        except UnicodeDecodeError:
            raise AuthenticationFailed("设备凭据无效。")
        if len(token) > 128:
            raise AuthenticationFailed("设备凭据无效。")
        device = AgentDevice.objects.select_related("owner").filter(token_digest=digest(token), revoked_at=None,
            expires_at__gt=timezone.now(), owner__is_active=True).first()
        if not device:
            raise AuthenticationFailed("设备凭据无效、过期或已撤销。")
        return device.owner, device

    def authenticate_header(self, request):
        return "Bearer"
