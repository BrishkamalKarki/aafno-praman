"""
The holder's transparency log: who checked my credentials, and when.

An unusual feature for a credential platform, and the one most worth keeping.
Normally verification is invisible to its subject — an employer phones a
university and the graduate never learns it happened. Surfacing it inverts that,
and the transparency is itself a control: verifiers who know the subject can see
them are materially less likely to go fishing.

## Two deliberate limits

**Anonymous scans are shown but never located.** A QR scan of a printed
certificate appears as "Anonymous scan" with no IP, city or device. The column
is a salted hash and must stay that way — a platform that told citizens the IP
of everyone who looked them up would be building a surveillance tool aimed at
recruiters, which is a worse harm than the one it solves.

**Named employer lookups are attributed.** This leaks a little of the employer's
hiring pipeline, and it is the right trade. It should be disclosed to verifiers
at signup rather than discovered.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from apps.common.permissions import IsCitizen

from .models import VerificationLog


class AccessLogEntrySerializer(serializers.ModelSerializer):
    verifier = serializers.SerializerMethodField()
    credential = serializers.SerializerMethodField()

    class Meta:
        model = VerificationLog
        fields = ["id", "verifier", "credential", "result", "created_at"]

    def get_verifier(self, log) -> str:
        # Falls back to the generic label rather than exposing the individual
        # user: the holder's legitimate interest is in which *organisation*
        # checked them, not which employee.
        if log.verifier_org_id:
            return log.verifier_org.legal_name
        return "Anonymous scan"

    def get_credential(self, log) -> str:
        record = log.record
        if record is None:
            return "A credential that has since been removed"
        detail = record.detail
        if detail is None:
            return record.get_record_type_display()
        return getattr(detail, "degree_title", None) or getattr(detail, "job_title", "")


@extend_schema(
    tags=["passport"],
    summary="Who has verified my credentials",
    description=(
        "Every verification of a credential belonging to the signed-in holder. "
        "Named organisations are identified; anonymous QR scans are listed "
        "without any location or device information."
    ),
)
class AccessLogView(generics.ListAPIView):
    serializer_class = AccessLogEntrySerializer
    permission_classes = [IsAuthenticated, IsCitizen]

    def get_queryset(self):
        # Scoped to the requester's own records. `request.identity` is set by
        # IsCitizen, so the filter can never be widened by a query parameter.
        identity = self.request.identity
        return (
            VerificationLog.objects.filter(record__subject=identity)
            .select_related("verifier_org", "record")
            .order_by("-created_at")
        )
