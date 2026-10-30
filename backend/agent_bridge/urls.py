from django.urls import path
from . import views

urlpatterns = [
    path("agent-devices/", views.DeviceList.as_view()),
    path("agent-devices/<uuid:pk>/revoke/", views.DeviceRevoke.as_view()),
    path("assistance-requests/", views.RequestList.as_view()),
    path("assistance-requests/<uuid:pk>/", views.RequestDetail.as_view()),
    path("assistance-requests/<uuid:pk>/cancel/", views.RequestCancel.as_view()),
    path("agent-runner/status/", views.RunnerStatus.as_view()),
    path("agent-runner/claim/", views.RunnerClaim.as_view()),
    path("agent-runner/requests/<uuid:pk>/heartbeat/", views.RunnerHeartbeat.as_view()),
    path("agent-runner/requests/<uuid:pk>/result/", views.RunnerResult.as_view()),
]
