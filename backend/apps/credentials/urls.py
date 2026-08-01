from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .confirm_views import ConfirmOfferView, DeclineOfferView, OfferPreviewView
from .offer_views import MyOfferViewSet
from .views import (
    BatchListView,
    BatchUploadView,
    ClaimReviewViewSet,
    ExperienceClaimView,
    IssueAcademicView,
    IssuedRecordViewSet,
    IssueExperienceView,
)

app_name = "credentials"

router = DefaultRouter()
router.register("records", IssuedRecordViewSet, basename="record")
router.register("claims", ClaimReviewViewSet, basename="claim")
# The signed-in half of the consent gate. The token routes below stay for
# holders who never create an account.
router.register("offers", MyOfferViewSet, basename="offer")

urlpatterns = [
    path("issue/academic/", IssueAcademicView.as_view(), name="issue-academic"),
    path("issue/experience/", IssueExperienceView.as_view(), name="issue-experience"),
    path("batches/upload/", BatchUploadView.as_view(), name="batch-upload"),
    path("batches/", BatchListView.as_view(), name="batch-list"),
    path("claim-experience/", ExperienceClaimView.as_view(), name="claim-experience"),
    # --- public confirmation ("is this you?") --------------------------------
    # No auth: the recipient may have no account, and forcing a signup before
    # they can say "wrong person" would be absurd. The token is the credential.
    path("confirm/<str:token>/", OfferPreviewView.as_view(), name="offer-preview"),
    path("confirm/<str:token>/accept/", ConfirmOfferView.as_view(), name="offer-accept"),
    path("confirm/<str:token>/decline/", DeclineOfferView.as_view(), name="offer-decline"),
    path("", include(router.urls)),
]
