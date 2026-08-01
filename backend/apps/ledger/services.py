"""
Anchoring service — the write path to the ledger.

The governing rule: **a chain failure must never lose a record.** The database is
written and committed first, then the chain is attempted. If the node is down the
record sits in ``PENDING_ANCHOR`` and ``manage.py anchor_pending`` finishes the
job later (E-09). The inverse ordering — chain first, then database — would risk
an anchor on chain with no off-chain record, which is unrecoverable because the
chain cannot be rewritten.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from eth_account import Account
from eth_account.messages import encode_defunct

from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.common.exceptions import IssuerNotApproved, LedgerUnavailable
from apps.credentials.models import CredentialRecord, RecordStatus
from apps.credentials.payloads import compute_dedupe_key, hash_record
from apps.organizations.keys import get_signer

from .client import (
    ISSUER_KIND_EMPLOYER,
    ISSUER_KIND_INSTITUTION,
    LedgerRejectedError,
    LedgerUnavailableError,
    get_ledger_client,
)
from .models import AnchorState, LedgerAnchor, RevocationEvent

logger = logging.getLogger(__name__)


def issuer_kind_for(organization) -> int:
    from apps.organizations.models import OrganizationKind

    return (
        ISSUER_KIND_INSTITUTION
        if organization.kind == OrganizationKind.INSTITUTION
        else ISSUER_KIND_EMPLOYER
    )


def ensure_gas(organization) -> bool:
    """
    Make sure an issuer can pay for its next transaction (HR-05).

    Called before every anchor. Tops up from the platform treasury when the
    balance is below the floor, and returns whether the issuer is fundable.

    A failure here is deliberately *not* fatal: the anchor attempt proceeds and,
    if it fails for lack of gas, the record lands in ``PENDING_ANCHOR`` like any
    other ledger outage and the retry command picks it up once the treasury is
    topped up. Refusing to issue because the platform's own gas ran out would
    punish the university for the platform's operational problem.
    """
    from django.conf import settings

    if not organization.chain_address:
        return False

    client = get_ledger_client()
    try:
        balance = client.balance_of(organization.chain_address)
        if balance >= settings.CHAIN["GAS_MIN_BALANCE_WEI"]:
            return True

        result = client.fund_issuer(organization.chain_address, settings.CHAIN["GAS_TOPUP_WEI"])
        logger.info(
            "Sponsored gas for %s: %s wei (tx=%s)",
            organization.slug,
            settings.CHAIN["GAS_TOPUP_WEI"],
            result.tx_hash,
        )
        return True
    except LedgerUnavailableError as exc:
        logger.warning("Could not sponsor gas for %s: %s", organization.slug, exc)
        return False


def sign_record_hash(private_key: str, record_hash: str) -> str:
    """
    Produce an EIP-191 signature over the record hash.

    Stored alongside the anchor so a QR code can be validated cryptographically
    even when the RPC endpoint is unreachable (HR-08). The UI shows that state as
    ``UNCONFIRMED`` — "signed by an approved issuer, chain not yet reachable" —
    which is materially different from, and much more useful than, an error page.
    """
    message = encode_defunct(hexstr=record_hash)
    signed = Account.from_key(private_key).sign_message(message)
    return signed.signature.hex()


@transaction.atomic
def freeze_record(
    record: CredentialRecord, *, target_status: str = RecordStatus.PENDING_ANCHOR
) -> CredentialRecord:
    """
    Compute and store the record's hash, canonical payload and dedupe key.

    After this commits, the record's data is contractually frozen: the hash is
    the platform's public commitment to those exact bytes. The unique index on
    ``dedupe_key`` fires here for a duplicate, before anything reaches the chain,
    so a re-uploaded CSV row is rejected without spending gas.

    ``target_status`` exists because freezing and anchoring are no longer the
    same moment. Under the consent gate a record freezes at ``OFFERED`` — the
    holder is shown the exact hash that will be published before they agree —
    and only reaches ``PENDING_ANCHOR`` once they confirm.
    """
    record_hash, payload = hash_record(record)
    record.record_hash = record_hash
    record.canonical_payload = payload
    record.dedupe_key = compute_dedupe_key(record)
    record.status = target_status
    record.save(
        update_fields=[
            "record_hash",
            "canonical_payload",
            "dedupe_key",
            "status",
            "updated_at",
        ]
    )
    return record


def anchor_record(record: CredentialRecord, *, actor=None, request=None) -> LedgerAnchor:
    """
    Anchor a single record.

    Returns the ``LedgerAnchor`` in whatever state it reached. The caller decides
    how to present a pending anchor; it is deliberately not an exception, because
    "saved, anchoring shortly" is a successful outcome from the issuer's point of
    view and the API returns 202 for it.
    """
    if not record.issuer.can_issue:
        raise IssuerNotApproved()

    if record.status not in {RecordStatus.PENDING_ANCHOR, RecordStatus.DRAFT}:
        if record.status == RecordStatus.ISSUED:
            existing = record.anchors.filter(state=AnchorState.CONFIRMED).first()
            if existing:
                return existing
        raise ValueError(f"Record {record.pk} cannot be anchored from status {record.status}.")

    if not record.record_hash:
        freeze_record(record)

    ensure_gas(record.issuer)
    address, private_key = get_signer(record.issuer)
    signature = sign_record_hash(private_key, record.record_hash)

    # Committed before the chain call, so a crash mid-transaction leaves a
    # diagnosable PENDING row rather than nothing at all.
    anchor = LedgerAnchor.objects.create(
        record=record,
        record_hash=record.record_hash,
        state=AnchorState.PENDING,
        issuer_address=address,
        issuer_signature=signature,
        attempts=1,
    )

    client = get_ledger_client()
    try:
        result = client.anchor(record.record_hash, private_key)
    except LedgerRejectedError as exc:
        return _handle_rejection(anchor, record, exc, actor=actor, request=request)
    except LedgerUnavailableError as exc:
        _mark_failed_attempt(anchor, str(exc))
        logger.warning("Ledger unavailable while anchoring %s: %s", record.pk, exc)
        record_event(
            AuditAction.RECORD_ANCHOR_FAILED,
            actor=actor,
            organization=record.issuer,
            obj=record,
            metadata={"reason": str(exc)[:300], "retryable": True},
            request=request,
        )
        return anchor
    finally:
        del private_key

    _confirm(anchor, result)
    record.mark_issued()
    record_event(
        AuditAction.RECORD_ANCHORED,
        actor=actor,
        organization=record.issuer,
        obj=record,
        metadata={
            "record_hash": record.record_hash,
            "tx_hash": result.tx_hash,
            "block_number": result.block_number,
        },
        request=request,
    )
    return anchor


def anchor_batch(records: list[CredentialRecord], *, actor=None, request=None) -> dict:
    """
    Anchor many records in one transaction — proposal §5.2 / FR-04.

    A registrar uploading 180 graduates should pay for one transaction, not 180.
    The contract reverts atomically, so either every record in the batch is
    anchored or none is, and there is no partially-issued graduating class to
    reconcile by hand.
    """
    if not records:
        return {"anchored": 0, "tx_hash": "", "state": AnchorState.FAILED}

    issuer = records[0].issuer
    if not issuer.can_issue:
        raise IssuerNotApproved()
    if any(r.issuer_id != issuer.pk for r in records):
        raise ValueError("Every record in a batch must belong to the same issuer.")

    for record in records:
        if not record.record_hash:
            freeze_record(record)

    ensure_gas(issuer)
    address, private_key = get_signer(issuer)
    hashes = [r.record_hash for r in records]

    anchors = [
        LedgerAnchor(
            record=record,
            record_hash=record.record_hash,
            state=AnchorState.PENDING,
            issuer_address=address,
            issuer_signature=sign_record_hash(private_key, record.record_hash),
            attempts=1,
        )
        for record in records
    ]
    LedgerAnchor.objects.bulk_create(anchors)

    client = get_ledger_client()
    try:
        result = client.anchor_batch(hashes, private_key)
    except (LedgerUnavailableError, LedgerRejectedError) as exc:
        retryable = isinstance(exc, LedgerUnavailableError)
        LedgerAnchor.objects.filter(pk__in=[a.pk for a in anchors]).update(
            state=AnchorState.PENDING if retryable else AnchorState.FAILED,
            last_error=str(exc)[:1000],
        )
        logger.warning("Batch anchor failed (retryable=%s): %s", retryable, exc)
        record_event(
            AuditAction.RECORD_ANCHOR_FAILED,
            actor=actor,
            organization=issuer,
            metadata={"count": len(records), "reason": str(exc)[:300], "retryable": retryable},
            request=request,
        )
        return {
            "anchored": 0,
            "tx_hash": "",
            "state": AnchorState.PENDING if retryable else AnchorState.FAILED,
            "error": str(exc),
        }
    finally:
        del private_key

    now = timezone.now()
    LedgerAnchor.objects.filter(pk__in=[a.pk for a in anchors]).update(
        state=AnchorState.CONFIRMED,
        tx_hash=result.tx_hash,
        block_number=result.block_number,
        chain_id=result.chain_id,
        contract_address=result.contract_address or "",
        gas_used=result.gas_used,
        confirmed_at=now,
        last_error="",
    )
    CredentialRecord.objects.filter(pk__in=[r.pk for r in records]).update(
        status=RecordStatus.ISSUED, issued_at=now, updated_at=now
    )
    record_event(
        AuditAction.RECORD_ANCHORED,
        actor=actor,
        organization=issuer,
        metadata={"count": len(records), "tx_hash": result.tx_hash, "batch": True},
        request=request,
    )
    return {
        "anchored": len(records),
        "tx_hash": result.tx_hash,
        "block_number": result.block_number,
        "gas_used": result.gas_used,
        "state": AnchorState.CONFIRMED,
    }


def revoke_record(
    record: CredentialRecord, *, reason: str, actor=None, request=None
) -> RevocationEvent:
    """Revoke an issued record on chain and off (HR-03)."""
    if record.status not in {RecordStatus.ISSUED, RecordStatus.PENDING_ANCHOR}:
        raise ValueError(f"Only issued records can be revoked (status={record.status}).")

    event = RevocationEvent.objects.create(record=record, reason=reason, revoked_by=actor)

    address, private_key = get_signer(record.issuer)
    try:
        result = get_ledger_client().revoke(record.record_hash, reason, private_key)
        event.tx_hash = result.tx_hash
        event.confirmed_on_chain = True
        event.save(update_fields=["tx_hash", "confirmed_on_chain", "updated_at"])
    except LedgerUnavailableError as exc:
        # The off-chain revocation stands and verification already reports
        # REVOKED, so the credential stops being presentable immediately. Only
        # the on-chain flag lags, and the retry command reconciles it.
        logger.warning("Revocation of %s not yet on chain: %s", record.pk, exc)
    finally:
        del private_key

    record.status = RecordStatus.REVOKED
    record.save(update_fields=["status", "updated_at"])

    record_event(
        AuditAction.RECORD_REVOKED,
        actor=actor,
        organization=record.issuer,
        obj=record,
        metadata={"reason": reason[:300], "tx_hash": event.tx_hash},
        request=request,
    )
    return event


def retry_pending_anchors(limit: int = 50) -> dict:
    """
    Reconcile records stuck in ``PENDING_ANCHOR``.

    Reconciles rather than blindly resubmitting: a transaction may have landed
    while the response was being lost, so ``isAnchored`` is checked first.
    Resubmitting without that check would revert with ``AlreadyAnchored`` and mark
    a perfectly good record as failed.
    """
    from django.conf import settings

    max_attempts = settings.CHAIN["MAX_ANCHOR_ATTEMPTS"]
    stuck = (
        LedgerAnchor.objects.select_related("record", "record__issuer")
        .filter(state=AnchorState.PENDING, attempts__lt=max_attempts)
        .order_by("created_at")[:limit]
    )

    summary = {"checked": 0, "reconciled": 0, "anchored": 0, "still_pending": 0, "failed": 0}
    client = get_ledger_client()

    for anchor in stuck:
        summary["checked"] += 1
        record = anchor.record

        try:
            if client.verify(anchor.record_hash).exists:
                _confirm(anchor, None)
                if record.status == RecordStatus.PENDING_ANCHOR:
                    record.mark_issued()
                summary["reconciled"] += 1
                continue
        except LedgerUnavailableError:
            summary["still_pending"] += 1
            continue

        try:
            anchor_record(record)
            summary["anchored"] += 1
        except LedgerUnavailableError:
            summary["still_pending"] += 1
        except Exception as exc:  # pragma: no cover - defensive
            _mark_failed_attempt(anchor, str(exc), fatal=True)
            summary["failed"] += 1
            logger.exception("Giving up on anchor %s", anchor.pk)

    return summary


# ------------------------------------------------------------------ internals


def _confirm(anchor: LedgerAnchor, result) -> None:
    anchor.state = AnchorState.CONFIRMED
    anchor.confirmed_at = timezone.now()
    anchor.last_error = ""
    if result is not None:
        anchor.tx_hash = result.tx_hash
        anchor.block_number = result.block_number
        anchor.chain_id = result.chain_id
        anchor.contract_address = result.contract_address or ""
        anchor.gas_used = result.gas_used
    anchor.save()


def _mark_failed_attempt(anchor: LedgerAnchor, error: str, *, fatal: bool = False) -> None:
    anchor.attempts += 1
    anchor.last_error = error[:1000]
    anchor.state = AnchorState.FAILED if fatal else AnchorState.PENDING
    anchor.save(update_fields=["attempts", "last_error", "state", "updated_at"])


def _handle_rejection(
    anchor: LedgerAnchor, record: CredentialRecord, exc: Exception, *, actor, request
) -> LedgerAnchor:
    """
    Handle a contract revert.

    ``AlreadyAnchored`` is the interesting case and is *not* an error: it means a
    previous attempt succeeded and only the response was lost. Treating it as a
    failure would mark a genuinely anchored credential as broken, so it is
    reconciled into a confirmed anchor instead.
    """
    message = str(exc)
    if "already been anchored" in message.lower():
        logger.info("Record %s was already anchored; reconciling.", record.pk)
        _confirm(anchor, None)
        if record.status != RecordStatus.ISSUED:
            record.mark_issued()
        return anchor

    _mark_failed_attempt(anchor, message, fatal=True)
    record_event(
        AuditAction.RECORD_ANCHOR_FAILED,
        actor=actor,
        organization=record.issuer,
        obj=record,
        metadata={"reason": message[:300], "retryable": False},
        request=request,
    )
    raise LedgerUnavailable(detail=message)
