"""
Public confirmation endpoints — the "is this you?" link.

Unauthenticated by design. The recipient is a graduate who has never visited the
platform; requiring an account before they can answer would mean forcing a
signup on someone who may want to say "no, wrong person". The token is the
credential.

Two properties follow from that and are enforced below:

* **GET never mutates.** Mail clients and link scanners prefetch URLs; a link
  that confirmed on load would have credentials accepted by antivirus software
  rather than by people. Reading the offer and answering it are separate verbs.
* **Every failure looks identical.** Expired, already answered, and never
  existed all return the same message, so a caller working through guessed
  tokens learns nothing about which ones are real.
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.throttling import ConfirmThrottle

from .confirmations import confirm_offer, decline_offer, peek_offer


class OfferPreviewSerializer(serializers.Serializer):
    """What the holder is shown before deciding. Read-only, no secrets."""

    record_id = serializers.UUIDField()
    record_type = serializers.CharField()
    issuer_name = serializers.CharField()
    subject_name = serializers.CharField()
    subject_email = serializers.EmailField()
    title = serializers.CharField()
    record_hash = serializers.CharField(
        help_text="The exact value that will be published if you confirm."
    )
    canonical_payload = serializers.JSONField(
        help_text="The precise data the hash was computed over."
    )
    offer_expires_at = serializers.DateTimeField()


class DeclineSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ConfirmResultSerializer(serializers.Serializer):
    status = serializers.CharField()
    detail = serializers.CharField()


def _preview(record) -> dict:
    from .notifications import _describe

    return {
        "record_id": record.pk,
        "record_type": record.record_type,
        "issuer_name": record.issuer.legal_name,
        "subject_name": record.subject_full_name,
        "subject_email": record.subject_email,
        "title": _describe(record),
        "record_hash": record.record_hash,
        "canonical_payload": record.canonical_payload,
        "offer_expires_at": record.offer_expires_at,
    }


@extend_schema_view(
    get=extend_schema(
        tags=["credentials"],
        summary="Read a pending credential offer",
        responses={200: OfferPreviewSerializer},
        description=(
            "Shows the holder exactly what will be published, including the "
            "hash and the data it covers, before they decide. Never mutates."
        ),
    )
)
class OfferPreviewView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ConfirmThrottle]

    def get(self, request, token: str):
        return Response(_preview(peek_offer(token)), status=status.HTTP_200_OK)


@extend_schema(
    tags=["credentials"],
    summary="Confirm a credential is yours",
    request=None,
    responses={200: ConfirmResultSerializer},
    description="Accepts the credential and queues it for anchoring to the ledger.",
)
class ConfirmOfferView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ConfirmThrottle]

    def post(self, request, token: str):
        record = confirm_offer(token, request=request)
        return Response(
            {
                "status": record.status,
                "detail": (
                    "Confirmed. This credential is being written to the ledger and "
                    "will appear in your dashboard shortly."
                ),
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["credentials"],
    summary="Decline a credential",
    request=DeclineSerializer,
    responses={200: ConfirmResultSerializer},
    description=(
        "Rejects the credential. Nothing is published. The issuing organisation "
        "is told so they can correct the address they had on file."
    ),
)
class DeclineOfferView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ConfirmThrottle]

    def post(self, request, token: str):
        serializer = DeclineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = decline_offer(
            token, reason=serializer.validated_data.get("reason", ""), request=request
        )
        return Response(
            {
                "status": record.status,
                "detail": (
                    "Declined. Nothing has been published, and the issuer has been "
                    "notified that this address is not yours."
                ),
            },
            status=status.HTTP_200_OK,
        )
