"""
The organisation's own slice of the audit trail.

Backs the issuer console's "Ledger activity" screen. The audit table already
records every anchor attempt, confirmation and revocation with its transaction
hash, so this is a read over evidence that exists rather than a second activity
log kept in parallel — two logs that can disagree are worse than one.

Scoped to ``request.organization``, which ``IsOrganizationMember`` derives from
the caller's membership row. There is no query parameter that can widen it, and
no registrar-style cross-organisation view here: platform-wide oversight lives
in the Django admin, where it is auditable in its own right.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from apps.common.permissions import IsOrganizationMember

from .models import AuditEvent

#: Human wording for the actions an organisation's staff should see. Anything
#: absent from this map is still returned, labelled with its raw action code —
#: silently hiding an event from an audit view would defeat the point.
ACTION_LABELS = {
    "ORG_APPLIED": "Organisation registered",
    "ORG_APPROVED": "Approved by the registrar",
    "ORG_REJECTED": "Application rejected",
    "ORG_SUSPENDED": "Issuing suspended",
    "ORG_REINSTATED": "Issuing reinstated",
    "ISSUER_KEY_CREATED": "Signing key created",
    "RECORD_DRAFTED": "Confirmation sent",
    "RECORD_CLAIMED": "Claim submitted",
    "RECORD_ENDORSED": "Credential confirmed",
    "RECORD_CLAIM_REJECTED": "Credential declined",
    "RECORD_ANCHORED": "Anchored on chain",
    "RECORD_ANCHOR_FAILED": "Anchor attempt failed",
    "RECORD_REVOKED": "Credential revoked",
    "RECORD_SUPERSEDED": "Credential superseded",
    "BATCH_UPLOADED": "Batch uploaded",
    "VERIFICATION_PERFORMED": "Verification performed",
}


class AuditEventSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    detail = serializers.SerializerMethodField()
    tx_hash = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "action",
            "label",
            "detail",
            "tx_hash",
            "actor_label",
            "object_type",
            "object_id",
            "created_at",
        ]
        read_only_fields = fields

    def get_label(self, event) -> str:
        return ACTION_LABELS.get(event.action, event.get_action_display())

    def get_tx_hash(self, event) -> str:
        return str(event.metadata.get("tx_hash") or "")

    def get_detail(self, event) -> str:
        """
        One line of context, assembled from whatever the event actually carried.

        Metadata shape varies by action, so this reads keys defensively rather
        than assuming any of them are present — an activity row that 500s
        because an older event lacks a field is a worse outcome than a row that
        says a little less.
        """
        meta = event.metadata or {}
        parts: list[str] = []

        if sent_to := meta.get("sent_to"):
            parts.append(f"awaiting reply from {sent_to}")
        if stage := meta.get("stage"):
            parts.append(stage.replace("_", " "))
        if reason := meta.get("reason"):
            parts.append(str(reason)[:120])
        if note := meta.get("note"):
            parts.append(str(note)[:120])
        if (accepted := meta.get("accepted")) is not None:
            parts.append(f"{accepted} of {meta.get('total', accepted)} rows accepted")
        if result := meta.get("result"):
            parts.append(f"result {result}")
        if address := meta.get("address"):
            parts.append(address)

        return " · ".join(parts)


@extend_schema(
    tags=["organizations"],
    summary="My organisation's activity and ledger events",
)
class OrganizationActivityView(generics.ListAPIView):
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ["action"]

    def get_queryset(self):
        return AuditEvent.objects.filter(organization=self.request.organization).order_by(
            "-created_at"
        )
