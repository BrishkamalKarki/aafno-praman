"""Operational endpoints that belong to no single domain app."""

from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(
    tags=["ops"],
    summary="Liveness and dependency health",
    description=(
        "Reports database and ledger reachability. Returns 503 when the database "
        "is down. A degraded ledger is reported as 200 with `ledger.ok = false`: "
        "verification still serves cached results when the chain is unreachable, "
        "so an unreachable node is not a reason to fail a load-balancer probe."
    ),
    responses={200: dict, 503: dict},
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    checks: dict[str, dict] = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = {"ok": True}
    except Exception as exc:  # pragma: no cover - depends on infra failure
        checks["database"] = {"ok": False, "error": str(exc)[:200]}

    # Imported lazily so a misconfigured chain cannot break the health endpoint
    # that is supposed to report on it.
    from apps.ledger.client import get_ledger_client

    try:
        client = get_ledger_client()
        checks["ledger"] = client.health()
    except Exception as exc:  # pragma: no cover
        checks["ledger"] = {"ok": False, "error": str(exc)[:200]}

    healthy = checks["database"]["ok"]
    return Response(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
