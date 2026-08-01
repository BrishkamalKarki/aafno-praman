"""
The consent gate: nothing reaches the ledger without the holder's agreement.

This is the property the whole redesign turns on. An anchor is permanent and
public — publishing a claim about someone before they agree cannot be undone, so
these tests assert the gate holds from every direction, not just the happy path.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.common.exceptions import ConflictError
from apps.credentials.confirmations import (
    OfferClosed,
    OfferNotFound,
    confirm_offer,
    decline_offer,
    expire_stale_offers,
    hash_token,
    peek_offer,
    resend_confirmation,
)
from apps.credentials.models import (
    CredentialConfirmation,
    CredentialRecord,
    RecordStatus,
    RecordType,
)
from apps.credentials.services import issue_record


@pytest.fixture
def academic_kwargs():
    return {
        "record_type": RecordType.ACADEMIC,
        "subject_email": "sita@example.com",
        "subject_full_name": "Sita Sharma",
        "detail_data": {
            "registration_number": "TU-2081-0042",
            "degree_title": "BSc Computer Science",
            "level": "BACHELORS",
            "graduation_date": timezone.now().date(),
        },
    }


@pytest.fixture
def offer(db, institution, academic_kwargs, django_capture_on_commit_callbacks):
    """
    An issued offer. Returns ``(record, token, confirmation)``.

    ``django_capture_on_commit_callbacks`` is required, not incidental: the
    confirmation email is sent from ``transaction.on_commit`` so that a record
    which fails to save can never produce a link that 404s. Under the default
    non-transactional test case nothing ever commits, so without this the
    callback would never fire and the outbox would stay empty.

    The token is read back out of the email because that is the only place the
    plaintext exists — which incidentally proves the message really was sent.
    """
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        record = issue_record(issuer=institution, actor=None, **academic_kwargs)
    confirmation = CredentialConfirmation.objects.get(record=record)
    token = mail.outbox[-1].body.split("/confirm/")[1].split()[0].strip()
    return record, token, confirmation


@pytest.mark.django_db
class TestOffering:
    def test_issuance_does_not_anchor(self, offer):
        """The headline guarantee. Issuing publishes nothing."""
        record, _token, _c = offer
        assert record.status == RecordStatus.OFFERED
        assert record.anchors.count() == 0

    def test_hash_is_committed_before_the_holder_decides(self, offer):
        """
        The holder is shown the exact value that will be published. If it were
        computed after they agreed, they would be consenting to a blank cheque.
        """
        record, _token, _c = offer
        assert len(record.record_hash) == 64
        assert record.canonical_payload

    def test_record_is_immutable_once_offered(self, offer):
        from apps.credentials.models import IMMUTABLE_STATUSES

        record, _token, _c = offer
        assert record.status in IMMUTABLE_STATUSES
        assert record.is_editable is False

    def test_confirmation_email_is_sent_to_the_supplied_address(self, offer):
        _record, _token, confirmation = offer
        assert confirmation.sent_to == "sita@example.com"
        assert mail.outbox[-1].to == ["sita@example.com"]

    def test_email_warns_against_forwarding(self, offer):
        """Anyone holding the link can answer; the copy has to say so."""
        assert "Do not forward" in mail.outbox[-1].body

    def test_only_the_token_hash_is_stored(self, offer):
        _record, token, confirmation = offer
        assert confirmation.token_hash == hash_token(token)
        assert token not in confirmation.token_hash

    def test_an_account_is_created_for_an_unknown_recipient(self, offer):
        from apps.accounts.models import SeekerProfile

        assert SeekerProfile.objects.filter(user__email="sita@example.com").exists()

    def test_duplicate_offer_is_rejected_before_an_email_is_sent(
        self, institution, academic_kwargs, offer
    ):
        sent_before = len(mail.outbox)
        with pytest.raises(ConflictError):
            issue_record(issuer=institution, actor=None, **academic_kwargs)
        assert len(mail.outbox) == sent_before


@pytest.mark.django_db
class TestPreview:
    def test_reading_an_offer_does_not_answer_it(self, offer):
        """
        Mail clients and link scanners prefetch URLs. A GET that confirmed would
        have credentials accepted by antivirus software rather than by people.
        """
        record, token, _c = offer
        peek_offer(token)
        peek_offer(token)
        record.refresh_from_db()
        assert record.status == RecordStatus.OFFERED

    def test_unknown_token_is_rejected(self, db):
        with pytest.raises(OfferNotFound):
            peek_offer("not-a-real-token")


@pytest.mark.django_db
class TestConfirming:
    def test_confirming_queues_the_anchor(self, offer):
        record, token, _c = offer
        confirm_offer(token)
        record.refresh_from_db()
        assert record.status in {RecordStatus.PENDING_ANCHOR, RecordStatus.ISSUED}
        assert record.subject_responded_at is not None

    def test_token_is_single_use(self, offer):
        _record, token, _c = offer
        confirm_offer(token)
        with pytest.raises(OfferClosed):
            confirm_offer(token)

    def test_a_confirmed_offer_cannot_then_be_declined(self, offer):
        _record, token, _c = offer
        confirm_offer(token)
        with pytest.raises(OfferClosed):
            decline_offer(token)

    def test_expired_token_is_rejected(self, offer):
        _record, token, confirmation = offer
        CredentialConfirmation.objects.filter(pk=confirmation.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        with pytest.raises(OfferClosed):
            confirm_offer(token)

    def test_exhausted_confirmation_is_rejected(self, offer):
        _record, token, confirmation = offer
        CredentialConfirmation.objects.filter(pk=confirmation.pk).update(
            attempts=CredentialConfirmation.MAX_ATTEMPTS
        )
        with pytest.raises(OfferClosed):
            confirm_offer(token)


@pytest.mark.django_db
class TestDeclining:
    def test_declining_publishes_nothing(self, offer):
        record, token, _c = offer
        decline_offer(token, reason="Not my degree")
        record.refresh_from_db()
        assert record.status == RecordStatus.DECLINED
        assert record.anchors.count() == 0

    def test_the_reason_survives_for_the_issuer(self, offer):
        """
        A declined record is hidden, not erased. The university needs to see
        that the address they had on file said "not me", or a wrong email is
        silently swallowed instead of corrected.
        """
        record, token, _c = offer
        decline_offer(token, reason="Wrong person")
        record.refresh_from_db()
        assert record.decline_reason == "Wrong person"
        assert CredentialRecord.objects.filter(pk=record.pk).exists()

    def test_declining_frees_the_credential_for_re_issue(self, offer, institution, academic_kwargs):
        """The whole point of excluding DECLINED from LIVE_STATUSES."""
        _record, token, _c = offer
        decline_offer(token)

        reissued = issue_record(issuer=institution, actor=None, **academic_kwargs)
        assert reissued.status == RecordStatus.OFFERED


@pytest.mark.django_db
class TestResend:
    def test_resend_invalidates_the_previous_link(self, offer):
        """Two working links for one credential is two chances to intercept."""
        record, old_token, _c = offer
        resend_confirmation(record)

        with pytest.raises(OfferNotFound):
            confirm_offer(old_token)

    def test_resend_is_capped(self, offer):
        record, _token, confirmation = offer
        CredentialConfirmation.objects.filter(pk=confirmation.pk).update(
            send_count=CredentialConfirmation.MAX_SENDS
        )
        with pytest.raises(ConflictError):
            resend_confirmation(record)

    def test_resend_on_an_answered_offer_is_rejected(self, offer):
        record, token, _c = offer
        confirm_offer(token)
        with pytest.raises(OfferClosed):
            resend_confirmation(record)


@pytest.mark.django_db
class TestExpiry:
    def test_stale_offers_lapse(self, offer):
        record, _token, _c = offer
        CredentialRecord.objects.filter(pk=record.pk).update(
            offer_expires_at=timezone.now() - timedelta(seconds=1)
        )
        assert expire_stale_offers() == 1
        record.refresh_from_db()
        assert record.status == RecordStatus.EXPIRED

    def test_live_offers_are_untouched(self, offer):
        record, _token, _c = offer
        assert expire_stale_offers() == 0
        record.refresh_from_db()
        assert record.status == RecordStatus.OFFERED

    def test_expiry_frees_the_credential_for_re_issue(self, offer, institution, academic_kwargs):
        """
        Otherwise an institution that mistyped a graduate's address could never
        issue to the correct one — the dedupe key would be held forever.
        """
        record, _token, _c = offer
        CredentialRecord.objects.filter(pk=record.pk).update(
            offer_expires_at=timezone.now() - timedelta(seconds=1)
        )
        expire_stale_offers()

        reissued = issue_record(issuer=institution, actor=None, **academic_kwargs)
        assert reissued.status == RecordStatus.OFFERED


@pytest.mark.django_db
class TestCitizenshipAttestationThroughIssuance:
    """
    The issuer supplies the citizenship number, or nobody does.

    This is what makes the two identity levels real: a holder can never raise
    their own, so `CITIZENSHIP` always means an approved organisation that holds
    the physical document vouched for it.
    """

    def test_issuing_without_a_number_leaves_the_holder_email_only(self, offer):
        from apps.accounts.models import IdentityLevel, SeekerProfile

        record, _token, _c = offer
        profile = SeekerProfile.objects.get(pk=record.subject_id)
        assert profile.identity_level == IdentityLevel.EMAIL_ONLY
        assert profile.has_citizenship is False

    def test_issuing_with_a_number_raises_the_identity_level(
        self, institution, academic_kwargs, django_capture_on_commit_callbacks
    ):
        from apps.accounts.models import IdentityLevel, SeekerProfile

        with django_capture_on_commit_callbacks(execute=True):
            record = issue_record(
                issuer=institution, actor=None, national_id="12-01-70-98765", **academic_kwargs
            )

        profile = SeekerProfile.objects.get(pk=record.subject_id)
        assert profile.identity_level == IdentityLevel.CITIZENSHIP
        assert profile.citizenship_verified_by_id == institution.pk

    def test_a_number_already_held_by_someone_else_fails_the_issuance(
        self, institution, academic_kwargs, holder, django_capture_on_commit_callbacks
    ):
        """
        Failing loudly is correct. Silently reassigning would let this issuer
        hijack the subject-match guarantee another one established.
        """
        from apps.accounts.services import CitizenshipConflict, attest_citizenship

        attest_citizenship(profile=holder, national_id="12-01-70-98765", organization=institution)

        other = {**academic_kwargs, "subject_email": "someone.else@example.com"}
        with pytest.raises(CitizenshipConflict):
            with django_capture_on_commit_callbacks(execute=True):
                issue_record(issuer=institution, actor=None, national_id="12-01-70-98765", **other)


@pytest.mark.django_db
class TestSubjectBinding:
    """
    The subject-match guarantee, and its honest limits.

    Only holders whose citizenship an approved issuer attested can be checked
    this way. For everyone else the answer is "we cannot know" — never "wrong
    person", which would accuse an honest candidate on the strength of a
    missing field.
    """

    def _issue(self, institution, kwargs, capture, national_id=""):
        with capture(execute=True):
            return issue_record(issuer=institution, actor=None, national_id=national_id, **kwargs)

    def test_binding_is_frozen_at_issuance(
        self, institution, academic_kwargs, django_capture_on_commit_callbacks
    ):
        record = self._issue(
            institution, academic_kwargs, django_capture_on_commit_callbacks, "12-01-70-98765"
        )
        assert len(record.subject_binding) == 64
        assert len(record.binding_salt) == 32

    def test_correct_citizen_matches(
        self, institution, academic_kwargs, django_capture_on_commit_callbacks
    ):
        from apps.verification.services import check_subject

        record = self._issue(
            institution, academic_kwargs, django_capture_on_commit_callbacks, "12-01-70-98765"
        )
        matched, _level = check_subject(record, claimed_national_id="12/01/70/98765")
        assert matched is True

    def test_different_citizen_is_the_fraud_case(
        self, institution, academic_kwargs, django_capture_on_commit_callbacks
    ):
        from apps.verification.services import check_subject

        record = self._issue(
            institution, academic_kwargs, django_capture_on_commit_callbacks, "12-01-70-98765"
        )
        matched, _level = check_subject(record, claimed_national_id="99-88-77-66655")
        assert matched is False

    def test_email_only_holder_yields_unknown_not_mismatch(
        self, institution, academic_kwargs, django_capture_on_commit_callbacks
    ):
        from apps.accounts.models import IdentityLevel
        from apps.verification.services import check_subject

        record = self._issue(institution, academic_kwargs, django_capture_on_commit_callbacks)
        matched, level = check_subject(record, claimed_national_id="12-01-70-98765")
        assert matched is None
        assert level == IdentityLevel.EMAIL_ONLY

    def test_no_claim_supplied_yields_unknown(
        self, institution, academic_kwargs, django_capture_on_commit_callbacks
    ):
        from apps.verification.services import check_subject

        record = self._issue(
            institution, academic_kwargs, django_capture_on_commit_callbacks, "12-01-70-98765"
        )
        matched, _level = check_subject(record)
        assert matched is None

    def test_reassigning_the_subject_is_detectable(
        self, institution, academic_kwargs, django_capture_on_commit_callbacks, holder
    ):
        """
        The subject FK is not hashed. Without the binding in the payload, an
        insider could move a genuine degree onto another account and every
        integrity check would still pass.
        """
        from apps.credentials.payloads import hash_record

        record = self._issue(
            institution, academic_kwargs, django_capture_on_commit_callbacks, "12-01-70-98765"
        )
        before, _ = hash_record(record)

        record.subject_binding = "0" * 64
        after, _ = hash_record(record)
        assert before != after


@pytest.mark.django_db
class TestDocumentVerification:
    """
    Possession of the document is the authorisation.

    The endpoint must never behave as a lookup: a caller with no file learns
    nothing, and a caller with a file learns only about that file.
    """

    def _upload(self, client, content=b"%PDF-1.4 fake", **extra):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return client.post(
            "/api/v1/verify/document/",
            {"document": SimpleUploadedFile("cert.pdf", content, "application/pdf"), **extra},
            format="multipart",
        )

    def test_unknown_document_is_not_found(self, client):
        from rest_framework.test import APIClient

        response = self._upload(APIClient())
        assert response.status_code == 200
        assert response.data["result"] == "NOT_FOUND"

    def test_response_never_confirms_a_person_exists(self, client):
        """
        A miss must look identical whether the citizen is on the platform or
        not, or the endpoint becomes the enumeration oracle it exists to avoid.
        """
        from rest_framework.test import APIClient

        response = self._upload(APIClient(), claimed_national_id="12-01-70-98765")
        assert response.data["result"] == "NOT_FOUND"
        assert response.data["subject_match"] is None
        assert response.data["subject_check_available"] is False
