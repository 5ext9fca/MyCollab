from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ProductionTemplateViewSet, DesignElementViewSet, CommentViewSet, MilestoneViewSet, MissionViewSet, TagListView
from .saved_views import SavedViewSet
from .my_work import MyWorkSummary, MyWorkMissions
from .workspace import WorkspaceGraphView, WorkspaceOverviewView

router = DefaultRouter()
router.register("saved-views", SavedViewSet, basename="saved-view")
router.register("production-templates", ProductionTemplateViewSet, basename="production-template")
router.register("design-elements", DesignElementViewSet, basename="design-element")
router.register("missions", MissionViewSet, basename="mission")
router.register("comments", CommentViewSet, basename="comment")
router.register("milestones", MilestoneViewSet, basename="milestone")

urlpatterns = router.urls + [
    path("my-work/summary/", MyWorkSummary.as_view()),
    path("my-work/missions/", MyWorkMissions.as_view()),
    path("tags/", TagListView.as_view(), name="tag-list"),
    path(
        "workspace/overview/",
        WorkspaceOverviewView.as_view(),
        name="workspace-overview",
    ),
    path("workspace/graph/", WorkspaceGraphView.as_view(), name="workspace-graph"),
]
