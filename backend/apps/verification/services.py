"""
Verification — the read path, and the platform's central claim.

A verification answers one question: *does the data in front of me match what the
issuer committed to the ledger?* Two independent checks answer it:

1. **Database integrity.** Rebuild the canonical payload from the live detail
   rows and recompute the hash. If it differs from the stored hash, the database
   was edited after issuance.

2. **Ledger integrity.** Ask the contract whether that hash is anchored, revoked
   or superseded.

Check 1 is what makes the platform honest about its own storage. A system that
only performed check 2 would happily report VERIFIED for a record whose grades an
insider had edited in Postgres, because it would be comparing the chain against a
stored hash that nobody re-derived. Recomputing from live data is the difference
between "we checked" and "we asserted".
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from apps.credentials.models import CredentialRecord, RecordStatus
from apps.credentials.payloads import hash_record
from apps.ledger.client import LedgerUnavailableError, get_ledger_client

from .models import VerificationLog, VerificationResult

logger = logging.getLogger(__name__)


@dataclass
class VerificationOutcome:
    """The full result of one verification, ready to be serialised."""

    result: str
    reason: str = ""
    record: CredentialRecord | None = None
    expected_hash: str = ""
    computed_hash: str = ""
    chain: dict[str, Any] = field(default_factory=dict)
    issuer: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0

    @property
    def is_verified(self) -> bool:
        return self.result == VerificationResult.VERIFIED


def verify_record(record: CredentialRecord | None, *, reference: str = "") -> VerificationOutcome:
    """Run both integrity checks against a record and classify the outcome."""
    started = time.perf_counter()

    if record is None:
        return VerificationOutcome(
            result=VerificationResult.NOT_FOUND,
            # Deliberately identical wording whether the record never existed or
            # the caller is not entitled to see it: a distinguishable message
            # would let anyone probe the registry for who holds what (E-12).
            reason="No verified record matches this reference.",
            latency_ms=_elapsed(started),
        )

    # A record that never reached the ledger cannot be "verified" — but it is not
    # forged either. Reported as UNCONFIRMED with an honest explanation.
    if record.status in {RecordStatus.DRAFT, RecordStatus.PENDING_REVIEW, RecordStatus.REJECTED}:
        return VerificationOutcome(
            result=VerificationResult.NOT_FOUND,
            reason="No verified record matches this reference.",
            latency_ms=_elapsed(started),
        )

    # ---- check 1: database integrity ---------------------------------------
    try:
        computed_hash, _payload = hash_record(record)
    except ValueError as exc:
        logger.error("Cannot rehash record %s: %s", record.pk, exc)
        return VerificationOutcome(
            result=VerificationResult.TAMPERED,
            reason="The record is incomplete and cannot be verified.",
            record=record,
            expected_hash=record.record_hash,
            latency_ms=_elapsed(started),
        )

    issuer_info = _issuer_snapshot(record)

    if computed_hash != record.record_hash:
        return VerificationOutcome(
            result=VerificationResult.TAMPERED,
            reason=(
                "The record's contents no longer match the hash committed at "
                "issuance. It has been altered since it was issued."
            ),
            record=record,
            expected_hash=record.record_hash,
            computed_hash=computed_hash,
            issuer=issuer_info,
            latency_ms=_elapsed(started),
        )

    # ---- check 2: ledger integrity -----------------------------------------
    try:
        state = get_ledger_client().verify(record.record_hash)
    except LedgerUnavailableError as exc:
        logger.warning("Ledger unreachable during verification of %s: %s", record.pk, exc)
        anchor = record.anchors.filter(issuer_signature__gt="").order_by("-created_at").first()
        return VerificationOutcome(
            result=VerificationResult.UNCONFIRMED,
            reason=(
                "The record's data is intact and signed by an approved issuer, but "
                "the ledger could not be reached to confirm the anchor. Try again "
                "shortly."
            ),
            record=record,
            expected_hash=record.record_hash,
            computed_hash=computed_hash,
            issuer=issuer_info,
            chain={
                "reachable": False,
                "issuer_signature": anchor.issuer_signature if anchor else "",
                "signed_by": anchor.issuer_address if anchor else "",
            },
            latency_ms=_elapsed(started),
        )

    if not state.exists:
        if record.status == RecordStatus.PENDING_ANCHOR:
            return VerificationOutcome(
                result=VerificationResult.UNCONFIRMED,
                reason="This record has been issued but is still awaiting its ledger anchor.",
                record=record,
                expected_hash=record.record_hash,
                computed_hash=computed_hash,
                issuer=issuer_info,
                chain={"reachable": True, "anchored": False},
                latency_ms=_elapsed(started),
            )
        # The database claims this was issued, yet the chain has no anchor for
        # it. That is precisely the fabricated-record case the ledger exists to
        # catch — a row inserted directly into the database, bypassing issuance.
        return VerificationOutcome(
            result=VerificationResult.TAMPERED,
            reason=(
                "This record claims to be issued but has no anchor on the ledger. "
                "It was not issued through a verified institution."
            ),
            record=record,
            expected_hash=record.record_hash,
            computed_hash=computed_hash,
            issuer=issuer_info,
            chain={"reachable": True, "anchored": False},
            latency_ms=_elapsed(started),
        )

    chain_info = {
        "reachable": True,
        "anchored": True,
        "issuer_address": state.issuer_address,
        "issuer_name_on_chain": state.issuer_name,
        "issuer_active": state.issuer_active,
        "anchored_at": _from_epoch(state.issued_at),
        "revoked": state.revoked,
        "revoked_at": _from_epoch(state.revoked_at),
        "revocation_reason": state.revocation_reason,
        "superseded_by_hash": state.superseded_by,
    }
    anchor = record.anchors.filter(tx_hash__gt="").order_by("-created_at").first()
    if anchor:
        chain_info.update(
            {
                "tx_hash": anchor.tx_hash,
                "block_number": anchor.block_number,
                "chain_id": anchor.chain_id,
                "contract_address": anchor.contract_address,
            }
        )

    if state.revoked:
        return VerificationOutcome(
            result=VerificationResult.REVOKED,
            reason=state.revocation_reason or "This record was revoked by its issuer.",
            record=record,
            expected_hash=record.record_hash,
            computed_hash=computed_hash,
            chain=chain_info,
            issuer=issuer_info,
            latency_ms=_elapsed(started),
        )

    if state.superseded_by:
        successor = CredentialRecord.objects.filter(record_hash=state.superseded_by).first()
        chain_info["superseded_by_record_id"] = str(successor.pk) if successor else ""
        return VerificationOutcome(
            result=VerificationResult.SUPERSEDED,
            reason=(
                "This record has been replaced by a corrected version issued by the "
                "same organisation."
            ),
            record=record,
            expected_hash=record.record_hash,
            computed_hash=computed_hash,
            chain=chain_info,
            issuer=issuer_info,
            latency_ms=_elapsed(started),
        )

    return VerificationOutcome(
        result=VerificationResult.VERIFIED,
        reason="The record matches the hash anchored by the issuing organisation.",
        record=record,
        expected_hash=record.record_hash,
        computed_hash=computed_hash,
        chain=chain_info,
        issuer=issuer_info,
        latency_ms=_elapsed(started),
    )


def find_record(reference: str) -> CredentialRecord | None:
    """
    Resolve a verifier's input to a record.

    Accepts a record UUID or a 64-character record hash — both are things a QR
    code or a shared link can carry. Notably it does **not** accept a name:
    fuzzy name lookup over a national credential registry is an enumeration
    tool, so name search is confined to profiles the seeker opted in to sharing
    (HR-07).
    """
    reference = (reference or "").strip()
    if not reference:
        return None

    queryset = CredentialRecord.objects.select_related(
        "issuer", "subject", "subject__user", "academic_detail", "experience_detail"
    )

    cleaned = reference[2:] if reference.startswith("0x") else reference
    if len(cleaned) == 64:
        try:
            int(cleaned, 16)
        except ValueError:
            pass
        else:
            return queryset.filter(record_hash=cleaned.lower()).first()

    try:
        return queryset.filter(pk=reference).first()
    except (ValueError, TypeError, DjangoValidationError):
        # Not a UUID either — an unparseable reference is simply "not found".
        return None


def log_verification(
    outcome: VerificationOutcome,
    *,
    reference: str = "",
    verifier_org=None,
    verifier_user=None,
    share_link=None,
    client_ip_hash: str = "",
    user_agent: str = "",
    counts_against_quota: bool = False,
) -> VerificationLog:
    """Persist a verification for metering (§9), analytics and abuse detection."""
    return VerificationLog.objects.create(
        record=outcome.record,
        record_hash=outcome.expected_hash,
        lookup_reference=reference[:128],
        result=outcome.result,
        verifier_org=verifier_org,
        verifier_user=verifier_user,
        share_link=share_link,
        client_ip_hash=client_ip_hash,
        user_agent=user_agent[:200],
        latency_ms=outcome.latency_ms,
        counts_against_quota=counts_against_quota,
    )


class QuotaService:
    """
    Employer verification quota — proposal §9's freemium tier, enforced.

    Counted from ``VerificationLog`` rather than a running counter column: a
    counter drifts whenever a request fails midway, and a billing number that
    silently drifts is worse than one query per lookup. The
    ``(verifier_org, -created_at)`` index keeps that query cheap.
    """

    @staticmethod
    def period_start() -> datetime:
        now = timezone.now()
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @classmethod
    def lookups_this_month(cls, organization) -> int:
        return VerificationLog.objects.filter(
            verifier_org=organization,
            counts_against_quota=True,
            created_at__gte=cls.period_start(),
        ).count()

    @classmethod
    def status_for(cls, organization) -> dict:
        subscription = getattr(organization, "subscription", None)
        used = cls.lookups_this_month(organization)

        if subscription is None or subscription.is_unlimited:
            return {
                "plan": subscription.plan if subscription else "FREE",
                "used": used,
                "limit": None,
                "remaining": None,
                "unlimited": True,
                "resets_at": cls._next_reset(),
            }

        limit = subscription.monthly_lookup_limit
        return {
            "plan": subscription.plan,
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "unlimited": False,
            "resets_at": cls._next_reset(),
        }

    @classmethod
    def has_capacity(cls, organization) -> bool:
        status = cls.status_for(organization)
        return status["unlimited"] or status["remaining"] > 0

    @staticmethod
    def _next_reset() -> datetime:
        start = QuotaService.period_start()
        return (
            start.replace(year=start.year + 1, month=1)
            if start.month == 12
            else start.replace(month=start.month + 1)
        )


# ------------------------------------------------------------------ helpers


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _from_epoch(value: int) -> str:
    """Convert a Solidity uint64 timestamp to an ISO string."""
    if not value:
        return ""
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def _issuer_snapshot(record: CredentialRecord) -> dict:
    issuer = record.issuer
    return {
        "id": str(issuer.pk),
        "name": issuer.legal_name,
        "kind": issuer.kind,
        "status": issuer.status,
        "chain_address": issuer.chain_address,
        # E-02: an issuer suspended today does not retroactively invalidate the
        # degrees it granted while accredited, but a verifier deserves to know.
        "suspended": issuer.status == "SUSPENDED",
    }


def check_subject(record, *, claimed_national_id: str = "") -> tuple[bool | None, str]:
    """
    Answer "does this genuine credential actually belong to the person named?"

    Returns ``(matched, identity_level)`` where ``matched`` is:

    * ``True``  — the claimed citizenship number matches the credential's frozen
      subject binding.
    * ``False`` — it does not. This is the fraud case: a real certificate
      presented by someone it was not issued to.
    * ``None``  — the question cannot be answered, either because the verifier
      supplied no number or because the holder is an email-only account with
      nothing to check against.

    ``None`` is deliberately not collapsed into ``False``. Reporting "wrong
    person" when the truth is "we have no way to know" would accuse an honest
    candidate on the strength of a missing field — the exact dishonest
    simplification the outcome enum exists to prevent.

    The comparison is constant-time (``binding_matches`` uses
    ``hmac.compare_digest``), which matters here specifically: this runs on the
    verifier path where an attacker controls the input and can time the reply.
    """
    from apps.accounts.identity import binding_matches
    from apps.accounts.models import IdentityLevel

    subject = getattr(record, "subject", None)
    level = subject.identity_level if subject else IdentityLevel.EMAIL_ONLY

    if not claimed_national_id:
        return None, level
    if not (record.subject_binding and record.binding_salt):
        return None, level

    matched = binding_matches(claimed_national_id, record.binding_salt, record.subject_binding)
    return matched, level
