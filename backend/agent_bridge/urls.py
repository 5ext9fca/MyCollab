from django.urls import path
from . import views
from . import execution_api as execution
from . import code_api as code
from . import interaction_api as interaction

urlpatterns = [
    path("assistance-requests/<uuid:pk>/interaction/", interaction.InteractionState.as_view()),
    path("agent-runner/requests/<uuid:pk>/interaction/open/", interaction.RunnerInteractionOpen.as_view()),
    path("agent-runner/requests/<uuid:pk>/interaction/exchange/", interaction.RunnerInteractionExchange.as_view()),
    path("code-executions/", code.CodeList.as_view()),
    path("code-executions/<uuid:pk>/", code.CodeDetail.as_view()),
    path("code-executions/<uuid:pk>/cancel/", code.CodeCancel.as_view()),
    path("agent-runner/requests/<uuid:pk>/code-manifest/", code.RunnerCodeManifest.as_view()),
    path("agent-runner/requests/<uuid:pk>/code-publish/", code.RunnerCodePublish.as_view()),
    path("mission-executions/", execution.ExecutionList.as_view()),
    path("mission-executions/<uuid:pk>/", execution.ExecutionDetail.as_view()),
    path("mission-executions/<uuid:pk>/cancel/", execution.ExecutionCancel.as_view()),
    path("agent-runner/requests/<uuid:pk>/candidates/", execution.RunnerManifest.as_view()),
    path("agent-runner/requests/<uuid:pk>/selection/", execution.RunnerSelection.as_view()),
    path("agent-runner/requests/<uuid:pk>/candidates/<str:key>/upload/", execution.RunnerUpload.as_view()),
    path("agent-runner/requests/<uuid:pk>/complete/", execution.RunnerComplete.as_view()),
    path("agent-runner/requests/<uuid:pk>/references/<uuid:file_id>/", execution.RunnerReference.as_view()),
    path("agent-devices/", views.DeviceList.as_view()),
    path("agent-devices/<uuid:pk>/revoke/", views.DeviceRevoke.as_view()),
    path("assistance-requests/", views.RequestList.as_view()),
    path("assistance-requests/<uuid:pk>/", views.RequestDetail.as_view()),
    path("assistance-requests/<uuid:pk>/cancel/", views.RequestCancel.as_view()),
    path("agent-runner/claim/", views.RunnerClaim.as_view()),
    path("agent-runner/requests/<uuid:pk>/heartbeat/", views.RunnerHeartbeat.as_view()),
    path("agent-runner/requests/<uuid:pk>/result/", views.RunnerResult.as_view()),
]
