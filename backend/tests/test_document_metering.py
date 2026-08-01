"""
Document verification must be metered and logged like every other lookup.

It was neither, and three screens depended on it being both: the employer's
quota meter never moved, their verification history stayed empty, and a
citizen's "who checked me" log recorded their prospective employer as an
anonymous scan. The last of those is the serious one — that transparency log is
the platform's central promise to holders, and its primary verification flow was
the one thing invisible to it.
"""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.credentials.models import AcademicDetail, RecordStatus, RecordType
from apps.credentials.services import issue_record
from apps.organizations.models import MembershipRole, OrganizationMembership, Plan, Subscription
from apps.verification.models import VerificationLog

#: Small, structurally plausible, and with a .pdf name — the upload validator
#: rejects anything else, which is what it is there for.
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def upload(name="degree.pdf", content=PDF):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


@pytest.fixture
def issuer_staff(db, institution):
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
def anchored_record(db, institution, issuer_staff, holder):
    """A confirmed, issued record with a document attached to look it up by."""
    record = issue_record(
        issuer=institution,
        actor=issuer_staff,
        record_type=RecordType.ACADEMIC,
        subject_email=holder.user.email,
        subject_full_name=holder.user.full_name,
        document=upload(),
        detail_data={
            "registration_number": "TU-METER-1",
            "degree_title": "BSc Computer Science",
            "level": AcademicDetail.Level.BACHELORS,
            "graduation_date": date(2026, 6, 1),
        },
    )
    # The chain is off in tests, so drive the record to ISSUED directly rather
    # than through an anchor that cannot happen here.
    from django.utils import timezone

    record.status = RecordStatus.ISSUED
    record.issued_at = timezone.now()
    record.save(update_fields=["status", "issued_at"])
    return record


@pytest.fixture
def employer_client(db, employer):
    user = User.objects.create_user(
        email="hr@leapfrog.com.np",
        password="a-long-enough-staff-password",
        full_name="Leapfrog HR",
        role=Role.ORG_MEMBER,
    )
    OrganizationMembership.objects.create(
        user=user, organization=employer, role=MembershipRole.OWNER
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def verify(client, **extra):
    return client.post(
        "/api/v1/verify/document/",
        {"document": upload(), **extra},
        format="multipart",
    )


@pytest.mark.django_db
class TestMetering:
    def test_an_employer_check_counts_against_the_quota(
        self, employer_client, employer, anchored_record
    ):
        Subscription.objects.update_or_create(
            organization=employer, defaults={"plan": Plan.FREE, "monthly_lookup_limit": 10}
        )
        assert verify(employer_client).status_code == 200

        quota = employer_client.get("/api/v1/verify/quota/")
        assert quota.data["used"] == 1
        assert quota.data["remaining"] == 9

    def test_it_appears_in_the_employers_history(self, employer_client, anchored_record):
        response = verify(employer_client)

        history = employer_client.get("/api/v1/verify/history/")
        rows = history.data["results"]
        assert len(rows) == 1
        # The chain is disabled in tests, so the honest verdict here is
        # UNCONFIRMED rather than VERIFIED — see the outcome table. What matters
        # is that the log records whatever the caller was actually told.
        assert rows[0]["result"] == response.data["result"]
        assert rows[0]["counts_against_quota"] is True
        assert rows[0]["subject_name"] == "Sita Sharma"

    def test_an_exhausted_quota_blocks_further_checks(
        self, employer_client, employer, anchored_record
    ):
        Subscription.objects.update_or_create(
            organization=employer, defaults={"plan": Plan.FREE, "monthly_lookup_limit": 1}
        )
        assert verify(employer_client).status_code == 200

        blocked = verify(employer_client)
        assert blocked.status_code == 429
        assert blocked.data["error"]["code"] == "quota_exceeded"

    def test_a_pro_plan_is_never_blocked(self, employer_client, employer, anchored_record):
        Subscription.objects.update_or_create(
            organization=employer, defaults={"plan": Plan.PRO, "monthly_lookup_limit": 0}
        )
        for _ in range(3):
            assert verify(employer_client).status_code == 200

    def test_an_anonymous_check_is_not_metered_to_anyone(self, db, anchored_record):
        response = verify(APIClient())
        assert response.status_code == 200

        log = VerificationLog.objects.get()
        assert log.verifier_org_id is None
        assert log.counts_against_quota is False


@pytest.mark.django_db
class TestTheHoldersAccessLog:
    def test_a_named_employer_is_attributed(
        self, employer_client, employer, anchored_record, holder
    ):
        verify(employer_client)

        holder.user.set_password("a-perfectly-ordinary-password")
        holder.user.save()
        client = APIClient()
        client.force_authenticate(user=holder.user)

        rows = client.get("/api/v1/passport/access-log/").data["results"]
        assert len(rows) == 1
        assert rows[0]["verifier"] == employer.legal_name
        assert rows[0]["credential"] == "BSc Computer Science"

    def test_an_anonymous_scan_stays_anonymous(self, db, anchored_record, holder):
        """
        Named lookups are attributed; anonymous ones are listed without any
        location or device information. Telling a citizen the IP of everyone who
        looked them up would build a surveillance record of recruiters.
        """
        verify(APIClient())

        client = APIClient()
        client.force_authenticate(user=holder.user)
        rows = client.get("/api/v1/passport/access-log/").data["results"]
        assert rows[0]["verifier"] == "Anonymous scan"

    def test_an_unmatched_document_reveals_nothing_and_is_still_logged(
        self, employer_client, anchored_record
    ):
        response = employer_client.post(
            "/api/v1/verify/document/",
            {"document": upload("other.pdf", PDF + b"different")},
            format="multipart",
        )
        assert response.status_code == 200
        assert response.data["result"] == "NOT_FOUND"

        log = VerificationLog.objects.get()
        assert log.record_id is None
        # The filename is never the reference: "sita-sharma-degree.pdf" would put
        # a name into a log the subject can read.
        assert log.lookup_reference.startswith("sha256:")
        assert "other" not in log.lookup_reference
