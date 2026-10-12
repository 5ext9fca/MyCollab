from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CommentViewSet, MilestoneViewSet, MissionViewSet, TagListView

router = DefaultRouter()
router.register("missions", MissionViewSet, basename="mission")
router.register("comments", CommentViewSet, basename="comment")
router.register("milestones", MilestoneViewSet, basename="milestone")

urlpatterns = router.urls + [
    path("tags/", TagListView.as_view(), name="tag-list"),
]
