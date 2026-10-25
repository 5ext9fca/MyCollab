from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, SubscriptionView
router = DefaultRouter()
router.register('notifications', NotificationViewSet, basename='notification')
urlpatterns = router.urls + [path('missions/<uuid:mission_id>/subscription/', SubscriptionView.as_view())]
