"""Admin-console API routes, mounted at ``/api/admin/``.

These power the SPA's own management page (``/manage``) and are separate from
Django Admin at ``/admin/``. All endpoints require ``is_staff``.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AdminRegistrationViewSet, AdminUserListView

router = DefaultRouter()
router.register("registrations", AdminRegistrationViewSet, basename="admin-registration")

urlpatterns = router.urls + [
    path("users/", AdminUserListView.as_view(), name="admin-user-list"),
]
