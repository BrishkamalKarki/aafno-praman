"""Ledger transparency endpoints.

Exposed publicly on purpose. A platform that claims to be blockchain-backed
should let anyone confirm which chain, which contract, and how many anchors —
without taking the platform's word for any of it.
"""

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.throttling import VerificationThrottle

from .client import LedgerUnavailableError, get_ledger_client
from .models import AnchorState, LedgerAnchor


@extend_schema(
    tags=["verification"],
    summary="Ledger status",
    description=(
        "Chain id, contract address, current block and anchor count. Everything a "
        "verifier needs to query the contract directly with their own tooling."
    ),
    responses=inline_serializer(
        name="LedgerStatus",
        fields={
            "ledger": serializers.DictField(),
            "local": serializers.DictField(child=serializers.IntegerField()),
        },
    ),
)
class LedgerStatusView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [VerificationThrottle]

    def get(self, request):
        try:
            health = get_ledger_client().health()
        except LedgerUnavailableError as exc:
            # `health()` already reports a node that is configured but
            # unreachable. This catches the earlier failure: the client cannot
            # be *constructed* at all — no contract address, an unparseable RPC
            # URL, a missing ABI.
            #
            # Letting that escape turned the one endpoint whose entire job is to
            # report ledger health into a 500 whenever the ledger was unhealthy.
            # The frontend's ledger banner reads exactly this endpoint to decide
            # whether to warn that anchoring is paused, so a misconfigured chain
            # showed every dashboard a failed request instead of the banner
            # written for that situation.
            health = {"ok": False, "enabled": True, "error": str(exc)[:200]}

        return Response(
            {
                "ledger": health,
                "local": {
                    "confirmed_anchors": LedgerAnchor.objects.filter(
                        state=AnchorState.CONFIRMED
                    ).count(),
                    "pending_anchors": LedgerAnchor.objects.filter(
                        state=AnchorState.PENDING
                    ).count(),
                    "failed_anchors": LedgerAnchor.objects.filter(state=AnchorState.FAILED).count(),
                },
            }
        )
