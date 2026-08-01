"""
Issuer onboarding: an organisation asks, the registrar decides.

This gate is the platform's root of trust and the one thing the blockchain
explicitly does not provide. Without it anyone could self-register as "Tribhuvan
University" and mint degrees, and the ledger would launder forgeries with
cryptographic confidence rather than prevent them.
"""

import pytest

from apps.common.exceptions import ConflictError
from apps.credentials.models import RecordType
from apps.credentials.services import issue_record
from apps.organizations.models import Organization, OrganizationKind, OrganizationStatus
from apps.organizations.services import (
    approve_organization,
    reinstate_organization,
    reject_organization,
    suspend_organization,
)


@pytest.fixture
def applicant(db):
    """An organisation that has applied but not yet been reviewed."""
    return Organization.objects.create(
        kind=OrganizationKind.INSTITUTION,
        legal_name="Kathmandu University",
        slug="kathmandu-university",
        registration_number="UGC-0042",
        contact_email="registrar@ku.edu.np",
        status=OrganizationStatus.PENDING,
    )


@pytest.fixture
def registrar(db):
    from apps.accounts.models import Role, User

    return User.objects.create_user(
        email="registrar@aafnopraman.np",
        password="a-very-long-registrar-password",
        full_name="Platform Registrar",
        role=Role.REGISTRAR,
    )


def academic_kwargs(email="grad@example.com"):
    from django.utils import timezone

    return {
        "record_type": RecordType.ACADEMIC,
        "subject_email": email,
        "subject_full_name": "Test Graduate",
        "detail_data": {
            "registration_number": "KU-1",
            "degree_title": "BSc Physics",
            "level": "BACHELORS",
            "graduation_date": timezone.now().date(),
        },
    }


@pytest.mark.django_db
class TestApplicationState:
    def test_a_pending_organisation_cannot_issue(self, applicant):
        """The whole point of the gate."""
        assert applicant.can_issue is False

    def test_a_pending_organisation_has_no_signing_key(self, applicant):
        assert applicant.chain_address == ""

    def test_approval_requires_a_chain_address(self, applicant):
        """
        Enforced by a database check constraint, not just service code. An
        APPROVED organisation with no signing address would fail confusingly at
        its first anchor rather than at the moment the invariant broke.
        """
        from django.db import IntegrityError, transaction

        with pytest.raises(IntegrityError), transaction.atomic():
            Organization.objects.filter(pk=applicant.pk).update(status=OrganizationStatus.APPROVED)


@pytest.mark.django_db
class TestApproval:
    def test_approval_opens_issuing(self, applicant, registrar, stub_ledger):
        approve_organization(applicant, registrar=registrar)
        applicant.refresh_from_db()

        assert applicant.status == OrganizationStatus.APPROVED
        assert applicant.chain_address != ""
        assert applicant.can_issue is True
        assert applicant.approved_by_id == registrar.pk

    def test_approval_generates_a_custodial_signing_key(self, applicant, registrar, stub_ledger):
        """
        No university registrar's office in Nepal manages a private key or buys
        gas, so the platform holds one on their behalf.
        """
        approve_organization(applicant, registrar=registrar)
        applicant.refresh_from_db()
        assert applicant.issuer_key.address == applicant.chain_address

    def test_approving_twice_is_rejected(self, applicant, registrar, stub_ledger):
        approve_organization(applicant, registrar=registrar)
        with pytest.raises(ConflictError):
            approve_organization(applicant, registrar=registrar)

    def test_an_approved_issuer_can_issue(
        self, applicant, registrar, stub_ledger, django_capture_on_commit_callbacks
    ):
        approve_organization(applicant, registrar=registrar)
        applicant.refresh_from_db()

        with django_capture_on_commit_callbacks(execute=True):
            record = issue_record(issuer=applicant, actor=registrar, **academic_kwargs())
        assert record.pk is not None


@pytest.mark.django_db
class TestRejectionAndSuspension:
    def test_rejection_keeps_the_reason(self, applicant, registrar):
        reject_organization(applicant, registrar=registrar, reason="Accreditation unverified")
        applicant.refresh_from_db()

        assert applicant.status == OrganizationStatus.REJECTED
        assert "Accreditation" in applicant.status_reason
        assert applicant.can_issue is False

    def test_suspension_stops_further_issuing(self, applicant, registrar, stub_ledger):
        approve_organization(applicant, registrar=registrar)
        suspend_organization(applicant, registrar=registrar, reason="Under investigation")
        applicant.refresh_from_db()

        assert applicant.status == OrganizationStatus.SUSPENDED
        assert applicant.can_issue is False

    def test_reinstatement_restores_issuing(self, applicant, registrar, stub_ledger):
        approve_organization(applicant, registrar=registrar)
        suspend_organization(applicant, registrar=registrar, reason="Under investigation")
        reinstate_organization(applicant, registrar=registrar)
        applicant.refresh_from_db()

        assert applicant.status == OrganizationStatus.APPROVED
        assert applicant.can_issue is True

    def test_suspension_does_not_invalidate_past_credentials(
        self, applicant, registrar, stub_ledger, django_capture_on_commit_callbacks
    ):
        """
        A graduate's degree must not evaporate because their university was
        suspended years later. The contract models this too — suspension is not
        retroactive there either.
        """
        approve_organization(applicant, registrar=registrar)
        applicant.refresh_from_db()
        with django_capture_on_commit_callbacks(execute=True):
            record = issue_record(issuer=applicant, actor=registrar, **academic_kwargs())

        suspend_organization(applicant, registrar=registrar, reason="Under investigation")

        record.refresh_from_db()
        assert record.record_hash != ""
        assert record.issuer_id == applicant.pk
