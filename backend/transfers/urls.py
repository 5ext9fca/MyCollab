from django.urls import path
from .views import CreateView, JoinView, OperationView

urlpatterns = [
    path("file-transfers/", CreateView.as_view()),
    path("file-transfers/join/", JoinView.as_view()),
    path("file-transfers/<uuid:transfer_id>/", OperationView.as_view()),
]
