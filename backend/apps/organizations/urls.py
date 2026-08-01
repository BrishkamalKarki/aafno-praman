from django.urls import path

from apps.audit.views import OrganizationActivityView

from .views import (
    MembershipListView,
    MyOrganizationView,
    OrganizationApplicationView,
    OrganizationDirectoryView,
    OrganizationDocumentView,
    SubscriptionView,
)

app_name = "organizations"

urlpatterns = [
    path("directory/", OrganizationDirectoryView.as_view(), name="directory"),
    path("apply/", OrganizationApplicationView.as_view(), name="apply"),
    path("me/", MyOrganizationView.as_view(), name="mine"),
    path("me/documents/", OrganizationDocumentView.as_view(), name="documents"),
    path("me/members/", MembershipListView.as_view(), name="members"),
    path("me/subscription/", SubscriptionView.as_view(), name="subscription"),
    path("me/activity/", OrganizationActivityView.as_view(), name="activity"),
]
