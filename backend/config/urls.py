from django.contrib import admin
from django.urls import include, path

from accounts.views import MemberListView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/admin/", include("accounts.admin_urls")),
    path("api/library/", include("library.urls")),
    path("api/members/", MemberListView.as_view(), name="member-list"),
    path("api/", include("notifications.urls")),
    path("api/", include("agent_bridge.urls")),
    path("api/", include("missions.urls")),
]
