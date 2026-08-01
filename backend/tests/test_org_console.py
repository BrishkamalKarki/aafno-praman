"""
The organisation console's own endpoints: plan and activity feed.

Both are reads over state the platform already keeps. The plan switch is the
exception — it writes, and the point of these tests is that it writes for real
(the quota actually changes) rather than flipping a label the metering ignores.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.organizations.models import MembershipRole, OrganizationMembership, Plan


def _member(organization, *, email, role):
    user = User.objects.create_user(
        email=email,
        password="a-long-enough-staff-password",
        full_name="Staff Member",
        role=Role.ORG_MEMBER,
    )
    OrganizationMembership.objects.create(user=user, organization=organization, role=role)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def owner_client(db, employer):
    return _member(employer, email="owner@leapfrog.com.np", role=MembershipRole.OWNER)


@pytest.fixture
def viewer_client(db, employer):
    return _member(employer, email="viewer@leapfrog.com.np", role=MembershipRole.VIEWER)


@pytest.mark.django_db
class TestPlan:
    def test_a_new_organisation_starts_on_the_free_plan(self, owner_client, settings):
        response = owner_client.get("/api/v1/organizations/me/subscription/")
        assert response.status_code == 200
        assert response.data["plan"] == Plan.FREE
        assert response.data["monthly_lookup_limit"] == settings.FREE_PLAN_MONTHLY_LOOKUPS

    def test_the_owner_can_switch_to_pro_and_the_quota_follows(self, owner_client):
        response = owner_client.patch(
            "/api/v1/organizations/me/subscription/", {"plan": "PRO"}, format="json"
        )
        assert response.status_code == 200, response.data
        assert response.data["plan"] == Plan.PRO
        # 0 means unlimited on the model. A plan label that did not move the
        # limit would be decoration, not a plan.
        assert response.data["monthly_lookup_limit"] == 0

        quota = owner_client.get("/api/v1/verify/quota/")
        assert quota.data["unlimited"] is True

    def test_downgrading_restores_the_configured_free_allowance(self, owner_client, settings):
        owner_client.patch("/api/v1/organizations/me/subscription/", {"plan": "PRO"}, format="json")
        response = owner_client.patch(
            "/api/v1/organizations/me/subscription/", {"plan": "FREE"}, format="json"
        )
        assert response.data["monthly_lookup_limit"] == settings.FREE_PLAN_MONTHLY_LOOKUPS

    def test_a_viewer_cannot_change_the_plan(self, viewer_client):
        response = viewer_client.patch(
            "/api/v1/organizations/me/subscription/", {"plan": "PRO"}, format="json"
        )
        assert response.status_code == 403

    def test_an_unknown_plan_is_rejected(self, owner_client):
        response = owner_client.patch(
            "/api/v1/organizations/me/subscription/", {"plan": "GOLD"}, format="json"
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestActivityFeed:
    def test_it_returns_this_organisations_events_with_a_readable_label(
        self, owner_client, employer
    ):
        record_event(
            AuditAction.ORG_APPROVED,
            organization=employer,
            obj=employer,
            metadata={"tx_hash": "0x" + "ab" * 32},
        )

        response = owner_client.get("/api/v1/organizations/me/activity/")
        assert response.status_code == 200

        rows = response.data["results"] if "results" in response.data else response.data
        approved = next(row for row in rows if row["action"] == "ORG_APPROVED")
        assert approved["label"] == "Approved by the registrar"
        assert approved["tx_hash"].startswith("0xab")

    def test_another_organisations_events_are_not_visible(
        self, owner_client, employer, institution
    ):
        record_event(AuditAction.ORG_APPROVED, organization=institution, obj=institution)

        response = owner_client.get("/api/v1/organizations/me/activity/")
        rows = response.data["results"] if "results" in response.data else response.data
        assert all(row["action"] != "ORG_APPROVED" for row in rows)
