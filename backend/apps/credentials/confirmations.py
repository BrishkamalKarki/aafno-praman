"""
The consent gate: offer a credential, and anchor it only once its subject agrees.

## The flow

    issuer submits ──► record frozen at OFFERED ──► email sent
                                 │
        holder confirms ─────────┼───────────► PENDING_ANCHOR ──► anchored ──► ISSUED
        holder declines ─────────┤
        nobody answers ──────────┘ (expires)

## Why the record is frozen at OFFERED rather than at anchor time

The holder is shown the exact hash that will be published. If the issuer could
still edit the degree title afterwards, the thing anchored would not be the
thing consented to — so ``OFFERED`` is in ``IMMUTABLE_STATUSES`` and the hash is
computed before the email goes out, not after the reply comes back.

## Why declining hides rather than erases

A declined record stays, with its reason, visible to the issuer and in the audit
trail. The holder controls **publication**; they do not control the
institution's own books. A university that issued a degree in good faith needs
to see that the address they had on file said "not me" — that is how a wrong
email gets corrected rather than silently swallowed.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.common.exceptions import ConflictError, DomainError

from .models import CredentialConfirmation, CredentialRecord, RecordStatus
from .notifications import send_confirmation_email

logger = logging.getLogger(__name__)

#: 256 bits. The token travels in a URL and is the only thing standing between a
#: stranger and answering on someone else's behalf.
TOKEN_BYTES = 32


class OfferNotFound(DomainError):
    status_code = 404
    default_code = "offer_not_found"
    default_detail = "This confirmation link is not valid."


class OfferClosed(DomainError):
    default_code = "offer_closed"
    default_detail = "This credential has already been answered or the link has expired."


def hash_token(token: str) -> str:
    """
    Hash a confirmation token for storage.

    Plain SHA-256, deliberately. Unlike a citizenship number the token is 256
    bits of uniform randomness — there is no keyspace to enumerate, so a pepper
    would protect against nothing while adding a rotation problem.
    """
    return hashlib.sha256(token.strip().encode()).hexdigest()


@transaction.atomic
def create_offer(record: CredentialRecord, *, actor=None, request=None) -> str:
    """
    Freeze a drafted record, mint a confirmation token and email it.

    Returns the plaintext token. It is returned rather than logged so that tests
    and the development console can reach it; nothing persists it.
    """
    from apps.ledger.services import freeze_record

    if record.status != RecordStatus.DRAFT:
        raise ConflictError(
            detail=f"Only a drafted record can be offered (status={record.status})."
        )

    # Computes the hash and dedupe key. The unique index fires here, before any
    # email is sent, so a duplicate offer costs the graduate nothing.
    freeze_record(record, target_status=RecordStatus.OFFERED)

    now = timezone.now()
    expires_at = now + timedelta(hours=settings.CREDENTIAL_CONFIRM_TTL_HOURS)

    record.offered_at = now
    record.offer_expires_at = expires_at
    record.save(update_fields=["offered_at", "offer_expires_at", "updated_at"])

    token = secrets.token_urlsafe(TOKEN_BYTES)
    CredentialConfirmation.objects.create(
        record=record,
        token_hash=hash_token(token),
        sent_to=record.subject_email,
        expires_at=expires_at,
        last_sent_at=now,
    )

    record_event(
        AuditAction.RECORD_DRAFTED,
        actor=actor,
        organization=record.issuer,
        obj=record,
        metadata={"stage": "offered", "sent_to": record.subject_email},
        request=request,
    )

    # After commit: an email naming a record that then failed to save would send
    # the holder to a link that 404s.
    transaction.on_commit(
        lambda: send_confirmation_email(record=record, token=token, to_email=record.subject_email)
    )
    return token


def _open_confirmation(token: str) -> CredentialConfirmation:
    """
    Resolve a token to an open confirmation, or raise.

    Every failure mode returns the same message. Distinguishing "no such token"
    from "already used" from "expired" would let someone holding a list of
    guessed tokens learn which ones correspond to real credentials.
    """
    confirmation = (
        CredentialConfirmation.objects.select_related("record", "record__issuer")
        .filter(token_hash=hash_token(token))
        .first()
    )
    if confirmation is None:
        raise OfferNotFound()
    if not confirmation.is_open:
        raise OfferClosed()
    return confirmation


def peek_offer(token: str) -> CredentialRecord:
    """
    Read what a confirmation link refers to, without answering it.

    Backs the confirmation page: the holder must see the issuer, the credential
    and the hash *before* deciding. A link that acted on load would make consent
    meaningless, and would be triggered by every mail client that prefetches
    URLs.
    """
    return _open_confirmation(token).record


def _lock_open_confirmation(**lookup) -> CredentialConfirmation:
    """
    Take the row lock on an open confirmation, however it was addressed.

    Two rapid clicks on the same link — or on the dashboard button that answers
    the same offer — must not produce two anchor attempts for one credential.

    ``of=("self",)`` locks only the confirmation row. Without it Postgres
    rejects the query outright: ``record__subject`` is a nullable FK, so
    select_related emits a LEFT OUTER JOIN, and FOR UPDATE cannot be applied to
    the nullable side of one. SQLite ignores select_for_update entirely, which
    is exactly why this passed in tests and failed on the real database.
    """
    confirmation = (
        CredentialConfirmation.objects.select_for_update(of=("self",))
        .select_related("record", "record__issuer", "record__subject")
        .filter(**lookup)
        .first()
    )
    if confirmation is None:
        raise OfferNotFound()
    if not confirmation.is_open:
        raise OfferClosed()
    return confirmation


@transaction.atomic
def confirm_offer(token: str, *, request=None) -> CredentialRecord:
    """The holder accepts from the emailed link. Moves the record into the anchor queue."""
    return _accept(_lock_open_confirmation(token_hash=hash_token(token)), request=request)


@transaction.atomic
def confirm_offer_for_record(record: CredentialRecord, *, request=None) -> CredentialRecord:
    """
    The holder accepts from their own dashboard.

    Same state transition as the emailed link, reached without a token because
    the caller is already authenticated *as* the subject — the view establishes
    that before calling here. The token path stays for people who never sign in.
    """
    return _accept(_lock_open_confirmation(record=record), request=request)


def _accept(confirmation: CredentialConfirmation, *, request=None) -> CredentialRecord:
    now = timezone.now()
    confirmation.confirmed_at = now
    confirmation.save(update_fields=["confirmed_at", "updated_at"])

    record = confirmation.record
    record.status = RecordStatus.PENDING_ANCHOR
    record.subject_responded_at = now
    record.save(update_fields=["status", "subject_responded_at", "updated_at"])

    record_event(
        AuditAction.RECORD_ENDORSED,
        organization=record.issuer,
        obj=record,
        metadata={"stage": "confirmed_by_holder"},
        request=request,
    )

    # Anchoring is attempted after commit so a ledger outage cannot roll back
    # the holder's consent — the record stays PENDING_ANCHOR and the retry
    # command finishes the job.
    transaction.on_commit(lambda: _anchor(record))
    return record


def _anchor(record: CredentialRecord) -> None:
    from apps.ledger.services import anchor_record

    try:
        anchor_record(record)
    except Exception:
        logger.exception("Anchor attempt failed for confirmed record %s", record.pk)


@transaction.atomic
def decline_offer(token: str, *, reason: str = "", request=None) -> CredentialRecord:
    """The holder says it is not theirs. Nothing is anchored, nothing is erased."""
    return _decline(
        _lock_open_confirmation(token_hash=hash_token(token)), reason=reason, request=request
    )


@transaction.atomic
def decline_offer_for_record(
    record: CredentialRecord, *, reason: str = "", request=None
) -> CredentialRecord:
    """The holder declines from their own dashboard. See ``confirm_offer_for_record``."""
    return _decline(_lock_open_confirmation(record=record), reason=reason, request=request)


def _decline(
    confirmation: CredentialConfirmation, *, reason: str = "", request=None
) -> CredentialRecord:
    now = timezone.now()
    confirmation.declined_at = now
    confirmation.save(update_fields=["declined_at", "updated_at"])

    record = confirmation.record
    record.status = RecordStatus.DECLINED
    record.subject_responded_at = now
    record.decline_reason = reason
    # Releasing the dedupe key is what lets the issuer correct the address and
    # re-offer. DECLINED is not in LIVE_STATUSES, so the partial unique index
    # stops covering this row automatically.
    record.save(update_fields=["status", "subject_responded_at", "decline_reason", "updated_at"])

    record_event(
        AuditAction.RECORD_CLAIM_REJECTED,
        organization=record.issuer,
        obj=record,
        metadata={"stage": "declined_by_holder", "reason": reason[:200]},
        request=request,
    )
    return record


@transaction.atomic
def resend_confirmation(record: CredentialRecord, *, actor=None, request=None) -> str:
    """
    Issue a fresh token for an outstanding offer and email it again.

    The old token is invalidated by replacing the hash, so a resend cannot leave
    two working links for one credential. ``MAX_SENDS`` bounds the total: an
    unbounded resend endpoint is a free mail-bomb aimed at any address the
    issuer names.
    """
    confirmation = CredentialConfirmation.objects.select_for_update().filter(record=record).first()
    if confirmation is None:
        raise OfferNotFound()
    if not confirmation.is_open:
        raise OfferClosed()
    if not confirmation.can_resend:
        raise ConflictError(
            detail=(
                "This confirmation has been sent the maximum number of times. "
                "Check the address on file before trying again."
            )
        )

    token = secrets.token_urlsafe(TOKEN_BYTES)
    confirmation.token_hash = hash_token(token)
    confirmation.send_count += 1
    confirmation.last_sent_at = timezone.now()
    confirmation.save(update_fields=["token_hash", "send_count", "last_sent_at", "updated_at"])

    transaction.on_commit(
        lambda: send_confirmation_email(record=record, token=token, to_email=confirmation.sent_to)
    )
    return token


def expire_stale_offers(limit: int = 500) -> int:
    """
    Lapse offers nobody answered.

    Run from a scheduled command. Without it, an unanswered offer holds the
    dedupe key for that credential forever, so an institution that mistyped a
    graduate's address could never re-issue to the correct one.
    """
    now = timezone.now()
    stale = list(
        CredentialRecord.objects.filter(
            status=RecordStatus.OFFERED, offer_expires_at__lt=now
        ).values_list("pk", flat=True)[:limit]
    )
    if not stale:
        return 0

    CredentialRecord.objects.filter(pk__in=stale).update(
        status=RecordStatus.EXPIRED, updated_at=now
    )
    logger.info("Expired %s unanswered credential offers", len(stale))
    return len(stale)
