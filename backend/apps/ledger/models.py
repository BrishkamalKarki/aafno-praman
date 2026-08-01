"""Ledger bookkeeping — the off-chain record of on-chain state."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_record_hash


class AnchorState(models.TextChoices):
    PENDING = "PENDING", _("Pending submission")
    CONFIRMED = "CONFIRMED", _("Confirmed on chain")
    FAILED = "FAILED", _("Failed")


class LedgerAnchor(BaseModel):
    """
    One attempt to write a record hash to the chain.

    Attempts are rows rather than overwritten columns (see ``docs/DATABASE.md``
    §2.4): when a node is down mid-batch, the operator needs to see what was
    tried and why it failed, not a single mutated status field.
    """

    record = models.ForeignKey(
        "credentials.CredentialRecord", on_delete=models.CASCADE, related_name="anchors"
    )
    record_hash = models.CharField(max_length=64, validators=[validate_record_hash], db_index=True)
    state = models.CharField(
        max_length=20, choices=AnchorState.choices, default=AnchorState.PENDING
    )

    chain_id = models.BigIntegerField(null=True, blank=True)
    contract_address = models.CharField(max_length=42, blank=True)
    tx_hash = models.CharField(max_length=66, blank=True, db_index=True)
    block_number = models.BigIntegerField(null=True, blank=True)
    gas_used = models.BigIntegerField(null=True, blank=True)

    issuer_address = models.CharField(max_length=42, blank=True)
    issuer_signature = models.CharField(
        max_length=132,
        blank=True,
        help_text=_(
            "EIP-191 signature over the record hash by the issuer key. Lets a "
            "verifier confirm authenticity from a QR code alone when the chain "
            "is unreachable (HR-08)."
        ),
    )

    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ledger_anchor"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["state", "attempts"]),
            models.Index(fields=["record", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.state} anchor for {self.record_hash[:12]}…"


class RevocationEvent(BaseModel):
    """
    A revocation, recorded off-chain alongside its transaction.

    The proposal never mentions revocation, but immutable must not mean
    uncorrectable (HR-03): degrees do get rescinded and employment records do get
    disputed. Kept as events rather than a boolean so the reason and the actor
    survive.
    """

    record = models.ForeignKey(
        "credentials.CredentialRecord", on_delete=models.CASCADE, related_name="revocations"
    )
    reason = models.TextField()
    revoked_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    tx_hash = models.CharField(max_length=66, blank=True)
    confirmed_on_chain = models.BooleanField(default=False)

    class Meta:
        db_table = "ledger_revocationevent"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Revocation of {self.record_id}: {self.reason[:50]}"
