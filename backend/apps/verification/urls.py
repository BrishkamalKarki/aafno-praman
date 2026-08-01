"""Public verification endpoints — no account required."""

from django.urls import path

from .document_views import DocumentVerifyView
from .views import (
    AnalyticsView,
    CandidateSearchView,
    QuotaView,
    SharedPassportView,
    UnlockShareLinkView,
    VerificationHistoryView,
    VerifyLookupView,
    VerifyRecordView,
)

app_name = "verification"

urlpatterns = [
    path("lookup/", VerifyLookupView.as_view(), name="lookup"),
    # Document-first: possession of the certificate is the authorisation, which
    # is what keeps this from being an enumeration oracle over citizens.
    path("document/", DocumentVerifyView.as_view(), name="document"),
    path("record/<str:reference>/", VerifyRecordView.as_view(), name="record"),
    path("share/<str:token>/", SharedPassportView.as_view(), name="share"),
    path("share/<str:token>/unlock/", UnlockShareLinkView.as_view(), name="share-unlock"),
    # Employer dashboard (authenticated)
    path("quota/", QuotaView.as_view(), name="quota"),
    path("history/", VerificationHistoryView.as_view(), name="history"),
    path("analytics/", AnalyticsView.as_view(), name="analytics"),
    path("candidates/", CandidateSearchView.as_view(), name="candidates"),
]
