from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ProductionTemplateViewSet, DesignElementViewSet, CommentViewSet, MilestoneViewSet, MissionViewSet, TagListView
from .workspace import WorkspaceGraphView, WorkspaceOverviewView

router = DefaultRouter()
router.register("production-templates", ProductionTemplateViewSet, basename="production-template")
router.register("design-elements", DesignElementViewSet, basename="design-element")
router.register("missions", MissionViewSet, basename="mission")
router.register("comments", CommentViewSet, basename="comment")
router.register("milestones", MilestoneViewSet, basename="milestone")

urlpatterns = router.urls + [
    path("tags/", TagListView.as_view(), name="tag-list"),
    path(
        "workspace/overview/",
        WorkspaceOverviewView.as_view(),
        name="workspace-overview",
    ),
    path("workspace/graph/", WorkspaceGraphView.as_view(), name="workspace-graph"),
]
