"""
Issuer onboarding — the platform's root of trust in code.

Approving an organisation is the single most consequential action on the
platform. Everything downstream inherits its authority from this step: once
approved, an organisation can mint credentials that employers across the country
will treat as proof. The registrar's off-platform diligence (accreditation
letters, PAN certificates, a phone call to the campus) is the actual security
control; this module just makes the outcome binding.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.common.exceptions import ConflictError, DomainError
from apps.ledger.client import LedgerRejectedError, LedgerUnavailableError, get_ledger_client
from apps.ledger.services import ensure_gas, issuer_kind_for

from .keys import create_issuer_key
from .models import Organization, OrganizationStatus, Plan, Subscription

logger = logging.getLogger(__name__)


class ApprovalFailed(DomainError):
    default_code = "approval_failed"
    default_detail = "The organisation could not be approved on the ledger."


@transaction.atomic
def approve_organization(organization: Organization, *, registrar, request=None) -> Organization:
    """
    Approve an organisation: generate its signing key, register it on chain,
    and open its billing tier.

    Unlike issuance, this is **chain-first** and atomic. An organisation marked
    APPROVED in the database but absent from the contract would fail at its first
    issuance with an opaque revert, and its staff would have no way to tell
    whether the fault was theirs. Better to fail the approval loudly and let the
    registrar retry.
    """
    if organization.status == OrganizationStatus.APPROVED:
        raise ConflictError(detail="This organisation is already approved.")

    issuer_key = create_issuer_key(organization)

    try:
        result = get_ledger_client().approve_issuer(
            issuer_key.address, issuer_kind_for(organization), organization.legal_name
        )
    except LedgerRejectedError as exc:
        raise ApprovalFailed(detail=str(exc)) from exc
    except LedgerUnavailableError as exc:
        raise ApprovalFailed(
            detail=(
                f"The ledger is unreachable, so the organisation was not approved: {exc}. "
                "No partial state has been saved — retry once the node is available."
            )
        ) from exc

    organization.mark_approved(
        registrar=registrar, tx_hash=result.tx_hash, chain_address=issuer_key.address
    )

    # Fund the new signing account so the organisation's first issuance works
    # without anyone at the university ever hearing the word "gas" (HR-05).
    # Non-fatal: an unfunded issuer still gets approved and its first anchor
    # simply waits in PENDING_ANCHOR until the treasury is topped up.
    ensure_gas(organization)

    Subscription.objects.get_or_create(
        organization=organization,
        defaults={"plan": Plan.FREE, "monthly_lookup_limit": _free_limit()},
    )

    record_event(
        AuditAction.ISSUER_KEY_CREATED,
        actor=registrar,
        organization=organization,
        obj=organization,
        metadata={"address": issuer_key.address},
        request=request,
    )
    record_event(
        AuditAction.ORG_APPROVED,
        actor=registrar,
        organization=organization,
        obj=organization,
        metadata={"tx_hash": result.tx_hash, "chain_address": issuer_key.address},
        request=request,
    )
    logger.info("Approved %s on chain (tx=%s)", organization.slug, result.tx_hash)
    return organization


def reject_organization(organization: Organization, *, registrar, reason: str, request=None):
    """Reject an application. Nothing touches the chain — it was never on it."""
    if organization.status == OrganizationStatus.APPROVED:
        raise ConflictError(
            detail="This organisation is already approved. Suspend it instead of rejecting it."
        )

    organization.status = OrganizationStatus.REJECTED
    organization.status_reason = reason
    organization.save(update_fields=["status", "status_reason", "updated_at"])

    record_event(
        AuditAction.ORG_REJECTED,
        actor=registrar,
        organization=organization,
        obj=organization,
        metadata={"reason": reason[:300]},
        request=request,
    )
    return organization


def suspend_organization(organization: Organization, *, registrar, reason: str, request=None):
    """
    Suspend an approved issuer.

    Not retroactive, by design and by contract (E-02). Credentials the
    organisation issued while accredited stay verifiable — punishing thousands of
    graduates for their college's later misconduct would be both unjust and a
    reason for nobody to trust the platform. What stops immediately is the
    ability to issue anything new.
    """
    if organization.status != OrganizationStatus.APPROVED:
        raise ConflictError(detail="Only an approved organisation can be suspended.")

    try:
        result = get_ledger_client().suspend_issuer(organization.chain_address, reason)
        tx_hash = result.tx_hash
    except (LedgerUnavailableError, LedgerRejectedError) as exc:
        # The off-chain block takes effect regardless: `can_issue` is checked on
        # every request, so a suspended issuer cannot issue even while the chain
        # write is outstanding.
        logger.warning("On-chain suspension of %s failed: %s", organization.slug, exc)
        tx_hash = ""

    organization.status = OrganizationStatus.SUSPENDED
    organization.status_reason = reason
    organization.suspended_at = timezone.now()
    organization.save(update_fields=["status", "status_reason", "suspended_at", "updated_at"])

    record_event(
        AuditAction.ORG_SUSPENDED,
        actor=registrar,
        organization=organization,
        obj=organization,
        metadata={"reason": reason[:300], "tx_hash": tx_hash, "on_chain": bool(tx_hash)},
        request=request,
    )
    return organization


def reinstate_organization(organization: Organization, *, registrar, request=None):
    """Restore a suspended issuer's ability to issue."""
    if organization.status != OrganizationStatus.SUSPENDED:
        raise ConflictError(detail="Only a suspended organisation can be reinstated.")

    try:
        result = get_ledger_client().reinstate_issuer(organization.chain_address)
        tx_hash = result.tx_hash
    except (LedgerUnavailableError, LedgerRejectedError) as exc:
        # Reinstatement must NOT proceed off-chain alone: the contract would
        # reject every anchor attempt, so the organisation would appear active in
        # the UI while silently unable to issue.
        raise ApprovalFailed(
            detail=f"Could not reinstate on the ledger, so nothing was changed: {exc}"
        ) from exc

    organization.status = OrganizationStatus.APPROVED
    organization.status_reason = ""
    organization.suspended_at = None
    organization.save(update_fields=["status", "status_reason", "suspended_at", "updated_at"])

    record_event(
        AuditAction.ORG_REINSTATED,
        actor=registrar,
        organization=organization,
        obj=organization,
        metadata={"tx_hash": tx_hash},
        request=request,
    )
    return organization


def _free_limit() -> int:
    from django.conf import settings

    return settings.FREE_PLAN_MONTHLY_LOOKUPS
