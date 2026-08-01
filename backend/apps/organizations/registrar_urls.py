from django.urls import path
from rest_framework.routers import DefaultRouter

from .provisioning import ProvisionOrganizationView, ProvisionSeekerView
from .views import RegistrarOrganizationViewSet

app_name = "registrar"

router = DefaultRouter()
router.register("organizations", RegistrarOrganizationViewSet, basename="organization")

urlpatterns = [
    path("provision/user/", ProvisionSeekerView.as_view(), name="provision-user"),
    path(
        "provision/organization/",
        ProvisionOrganizationView.as_view(),
        name="provision-organization",
    ),
    *router.urls,
]
