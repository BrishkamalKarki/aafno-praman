"""
The holder's own inbox of pending credential offers.

The emailed "is this you?" link (``confirm_views``) covers the graduate who has
never signed in. This module covers the other half of the same consent gate: a
holder who *is* signed in should be able to answer from their dashboard without
hunting for an email, and a link that has been lost to a full inbox must not
strand a credential forever.

The security argument is unchanged, only re-derived from a different fact. On
the token path the token proves the answerer controls the mailbox the issuer
named. Here the session proves they control the account the record was linked
to, and that link was itself established by mailbox possession at registration.
Neither path lets a third party answer for someone else, which is the property
that matters.
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import IsCitizen, IsSubjectOfRecord

from .confirm_views import DeclineSerializer
from .confirmations import confirm_offer_for_record, decline_offer_for_record
from .models import CredentialRecord, RecordStatus
from .serializers import CredentialRecordSerializer


class OfferSerializer(CredentialRecordSerializer):
    """A pending offer, with the one extra field the decision needs."""

    title = serializers.SerializerMethodField()

    class Meta(CredentialRecordSerializer.Meta):
        fields = [
            *CredentialRecordSerializer.Meta.fields,
            "title",
            "offered_at",
            "offer_expires_at",
        ]
        read_only_fields = fields

    def get_title(self, record) -> str:
        from .notifications import _describe

        return _describe(record)


@extend_schema_view(
    list=extend_schema(tags=["passport"], summary="Credential offers awaiting my answer"),
    retrieve=extend_schema(tags=["passport"], summary="One pending offer"),
)
class MyOfferViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Offers addressed to the signed-in holder.

    Scoped to ``subject`` rather than ``subject_email`` so that an address later
    reassigned to a different person cannot surface someone else's pending
    degree — the link between record and account is made once, at registration,
    and is not re-derived per request.
    """

    serializer_class = OfferSerializer
    permission_classes = [IsAuthenticated, IsCitizen, IsSubjectOfRecord]

    def get_queryset(self):
        return (
            CredentialRecord.objects.filter(
                subject=self.request.user.seeker_profile, status=RecordStatus.OFFERED
            )
            .select_related("issuer", "academic_detail", "experience_detail")
            .prefetch_related("anchors")
            .order_by("-offered_at")
        )

    @extend_schema(summary="Confirm this credential is mine", request=None)
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        record = confirm_offer_for_record(self.get_object(), request=request)
        record.refresh_from_db()
        return Response(
            {
                "status": record.status,
                "detail": (
                    "Confirmed. This credential is being written to the ledger and "
                    "will appear in your dashboard shortly."
                ),
                "record": OfferSerializer(record).data,
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(summary="Decline this credential", request=DeclineSerializer)
    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        serializer = DeclineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record = decline_offer_for_record(
            self.get_object(),
            reason=serializer.validated_data.get("reason", ""),
            request=request,
        )
        return Response(
            {
                "status": record.status,
                "detail": (
                    "Declined. Nothing has been published, and the issuer has been "
                    "notified that this address is not yours."
                ),
                "record": OfferSerializer(record).data,
            },
            status=status.HTTP_200_OK,
        )
