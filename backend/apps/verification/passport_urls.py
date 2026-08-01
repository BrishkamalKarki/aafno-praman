"""Job seeker passport endpoints (authenticated)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .access_log_views import AccessLogView
from .views import MyPassportView, ShareLinkQRView, ShareLinkViewSet

app_name = "passport"

router = DefaultRouter()
router.register("share-links", ShareLinkViewSet, basename="share-link")

urlpatterns = [
    path("", MyPassportView.as_view(), name="mine"),
    path("access-log/", AccessLogView.as_view(), name="access-log"),
    path("share-links/<uuid:pk>/qr/", ShareLinkQRView.as_view(), name="share-link-qr"),
    path("", include(router.urls)),
]
