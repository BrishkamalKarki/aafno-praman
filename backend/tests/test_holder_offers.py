"""
The signed-in half of the consent gate.

A holder who *is* logged in should not have to find an email to answer an offer.
These tests pin the two properties that make the dashboard route safe to add
alongside the token route: it answers only the caller's own offers, and it makes
exactly the same state transition as the emailed link.
"""

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.accounts.services import get_or_create_account
from apps.credentials.models import AcademicDetail, CredentialRecord, RecordStatus, RecordType
from apps.credentials.services import issue_record


def academic_kwargs(email: str, name: str, registration_number: str) -> dict:
    return {
        "record_type": RecordType.ACADEMIC,
        "subject_email": email,
        "subject_full_name": name,
        "detail_data": {
            "registration_number": registration_number,
            "degree_title": "BSc Computer Science",
            "level": AcademicDetail.Level.BACHELORS,
            "graduation_date": date(2026, 6, 1),
        },
    }


@pytest.fixture
def issuer_staff(db, institution):
    from apps.organizations.models import MembershipRole, OrganizationMembership

    user = User.objects.create_user(
        email="staff@tu.edu.np",
        password="a-long-enough-staff-password",
        full_name="TU Registrar Office",
        role=Role.ORG_MEMBER,
    )
    OrganizationMembership.objects.create(
        user=user, organization=institution, role=MembershipRole.OWNER
    )
    return user


@pytest.fixture
def offer(db, institution, issuer_staff, holder):
    return issue_record(
        issuer=institution,
        actor=issuer_staff,
        **academic_kwargs(holder.user.email, holder.user.full_name, "TU-1"),
    )


@pytest.fixture
def holder_client(holder):
    holder.user.set_password("a-perfectly-ordinary-password")
    holder.user.save()
    client = APIClient()
    client.force_authenticate(user=holder.user)
    return client


@pytest.mark.django_db
class TestOfferInbox:
    def test_an_offer_appears_in_the_holders_inbox(self, holder_client, offer):
        response = holder_client.get("/api/v1/credentials/offers/")
        assert response.status_code == 200

        results = response.data["results"] if "results" in response.data else response.data
        assert [str(row["id"]) for row in results] == [str(offer.pk)]
        # The title is what the dashboard shows above the accept/decline buttons,
        # so an offer that cannot describe itself is not answerable.
        assert results[0]["title"]
        assert results[0]["issuer_name"] == "Tribhuvan University"

    def test_only_offers_are_listed(self, holder_client, offer):
        from django.utils import timezone

        offer.status = RecordStatus.ISSUED
        offer.issued_at = timezone.now()  # a CHECK constraint requires it
        offer.save(update_fields=["status", "issued_at"])

        response = holder_client.get("/api/v1/credentials/offers/")
        results = response.data["results"] if "results" in response.data else response.data
        assert results == []

    def test_another_holders_offer_is_invisible(self, db, offer, institution, issuer_staff):
        other, _ = get_or_create_account(email="ram@example.com", full_name="Ram Thapa")
        other.user.set_password("another-ordinary-password")
        other.user.save()

        client = APIClient()
        client.force_authenticate(user=other.user)
        response = client.get("/api/v1/credentials/offers/")
        results = response.data["results"] if "results" in response.data else response.data
        assert results == []

        # And not answerable by id either — invisibility that a guessed URL
        # defeats is not a boundary.
        assert client.post(f"/api/v1/credentials/offers/{offer.pk}/accept/").status_code == 404


@pytest.mark.django_db
class TestAnswerFromDashboard:
    def test_accepting_queues_the_record_for_anchoring(self, holder_client, offer):
        response = holder_client.post(f"/api/v1/credentials/offers/{offer.pk}/accept/")
        assert response.status_code == 200, response.data

        offer.refresh_from_db()
        # The chain is disabled in tests, so the record stops at PENDING_ANCHOR
        # and the retry command finishes it — exactly as it would after a real
        # node outage.
        assert offer.status == RecordStatus.PENDING_ANCHOR
        assert offer.subject_responded_at is not None

    def test_declining_records_the_reason_and_publishes_nothing(self, holder_client, offer):
        response = holder_client.post(
            f"/api/v1/credentials/offers/{offer.pk}/decline/",
            {"reason": "I never studied there."},
            format="json",
        )
        assert response.status_code == 200, response.data

        offer.refresh_from_db()
        assert offer.status == RecordStatus.DECLINED
        assert offer.decline_reason == "I never studied there."
        assert not offer.anchors.exists()

    def test_an_offer_cannot_be_answered_twice(self, holder_client, offer):
        assert (
            holder_client.post(f"/api/v1/credentials/offers/{offer.pk}/accept/").status_code == 200
        )
        # Second click: no longer in the queryset, because it is no longer OFFERED.
        second = holder_client.post(f"/api/v1/credentials/offers/{offer.pk}/accept/")
        assert second.status_code == 404

    def test_declining_releases_the_slot_so_the_issuer_can_re_offer(
        self, holder_client, offer, institution, issuer_staff
    ):
        holder_client.post(
            f"/api/v1/credentials/offers/{offer.pk}/decline/",
            {"reason": "Wrong address."},
            format="json",
        )
        reissued = issue_record(
            issuer=institution,
            actor=issuer_staff,
            **academic_kwargs("sita.correct@example.com", "Sita Sharma", "TU-1"),
        )
        assert reissued.status == RecordStatus.OFFERED
        assert CredentialRecord.objects.filter(issuer=institution).count() == 2

    def test_an_organisation_account_has_no_offer_inbox(self, db, issuer_staff):
        client = APIClient()
        client.force_authenticate(user=issuer_staff)
        assert client.get("/api/v1/credentials/offers/").status_code == 403


@pytest.mark.django_db
class TestPassportSummary:
    def test_the_summary_counts_offers_awaiting_an_answer(self, holder_client, offer):
        response = holder_client.get("/api/v1/passport/")
        assert response.status_code == 200
        assert response.data["summary"]["offered"] == 1
        assert response.data["summary"]["issued"] == 0
