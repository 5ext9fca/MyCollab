from rest_framework.routers import DefaultRouter

from .views import LibraryFileViewSet

router = DefaultRouter()
router.register("files", LibraryFileViewSet, basename="library-file")

urlpatterns = router.urls
