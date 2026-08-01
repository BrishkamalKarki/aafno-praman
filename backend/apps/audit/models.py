"""
Append-only audit trail.

Needed for three separate reasons, any one of which would justify it:

* The platform holds custodial signing keys, so there must be an independent
  record of every signature it produced on an issuer's behalf.
* Proposal §8 Phase II flags employer reluctance to endorse records "if there is
  dispute risk". A dispute is unresolvable without a log of who did what, when.
* Issuer compromise is the platform's worst-case attack; the audit trail is how
  the blast radius gets measured after the fact.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import UUIDModel


class AuditAction(models.TextChoices):
    # Accounts
    USER_REGISTERED = "USER_REGISTERED", _("User registered")
    USER_LOGGED_IN = "USER_LOGGED_IN", _("User logged in")
    # Registrar
    ORG_APPLIED = "ORG_APPLIED", _("Organisation applied")
    ORG_APPROVED = "ORG_APPROVED", _("Organisation approved")
    ORG_REJECTED = "ORG_REJECTED", _("Organisation rejected")
    ORG_SUSPENDED = "ORG_SUSPENDED", _("Organisation suspended")
    ORG_REINSTATED = "ORG_REINSTATED", _("Organisation reinstated")
    ISSUER_KEY_CREATED = "ISSUER_KEY_CREATED", _("Issuer signing key created")
    # Issuance
    RECORD_DRAFTED = "RECORD_DRAFTED", _("Record drafted")
    RECORD_CLAIMED = "RECORD_CLAIMED", _("Record claimed by seeker")
    RECORD_ENDORSED = "RECORD_ENDORSED", _("Claim endorsed by issuer")
    RECORD_CLAIM_REJECTED = "RECORD_CLAIM_REJECTED", _("Claim rejected by issuer")
    RECORD_ANCHORED = "RECORD_ANCHORED", _("Record anchored on chain")
    RECORD_ANCHOR_FAILED = "RECORD_ANCHOR_FAILED", _("Anchor attempt failed")
    RECORD_REVOKED = "RECORD_REVOKED", _("Record revoked")
    RECORD_SUPERSEDED = "RECORD_SUPERSEDED", _("Record superseded")
    BATCH_UPLOADED = "BATCH_UPLOADED", _("Batch uploaded")
    # Sharing and verification
    SHARE_LINK_CREATED = "SHARE_LINK_CREATED", _("Share link created")
    SHARE_LINK_REVOKED = "SHARE_LINK_REVOKED", _("Share link revoked")
    VERIFICATION_PERFORMED = "VERIFICATION_PERFORMED", _("Verification performed")


class AuditEvent(UUIDModel):
    """
    One recorded action.

    Never updated and never deleted by application code — there is no ``save``
    override, no admin edit permission, and nothing in the API that writes to it
    twice. An audit row that can be amended is not evidence.
    """

    action = models.CharField(max_length=32, choices=AuditAction.choices, db_index=True)
    actor = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_label = models.CharField(
        max_length=254,
        blank=True,
        help_text=_(
            "Denormalised actor identity. Kept because the FK is SET_NULL on user "
            "deletion, and an audit entry that loses its actor is worthless."
        ),
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    object_type = models.CharField(max_length=50, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    client_ip_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_event"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} by {self.actor_label or 'system'}"
