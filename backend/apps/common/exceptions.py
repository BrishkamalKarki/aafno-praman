"""
Uniform error envelope.

Every non-2xx response from the API has the same shape, so the frontend has one
error path instead of guessing between DRF's several native formats:

    {
      "error": {
        "code": "validation_error",
        "message": "Human-readable summary.",
        "details": {"field": ["what is wrong"]}
      }
    }
"""

import logging

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class DomainError(APIException):
    """
    Base for business-rule violations.

    Subclasses carry a stable machine-readable `code` that the frontend can
    branch on without string-matching the human message.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "domain_error"
    default_detail = "The request could not be completed."


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "This resource already exists."


class IssuerNotApproved(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "issuer_not_approved"
    default_detail = (
        "Your organisation is not an approved issuer. "
        "The platform registrar must approve it before you can issue records."
    )


class LedgerUnavailable(DomainError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "ledger_unavailable"
    default_detail = (
        "The ledger is temporarily unreachable. The record has been saved and "
        "will be anchored automatically."
    )


class QuotaExceeded(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "quota_exceeded"
    default_detail = "Monthly verification quota exhausted for your plan."


class ShareLinkExpired(DomainError):
    status_code = status.HTTP_410_GONE
    default_code = "share_link_expired"
    default_detail = "This share link has expired or been revoked."


CODE_BY_STATUS = {
    400: "validation_error",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    410: "gone",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "throttled",
    500: "server_error",
    503: "service_unavailable",
}


def _summarise(detail) -> str:
    """Pull a single human sentence out of DRF's nested detail structures."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        return _summarise(detail[0])
    if isinstance(detail, dict) and detail:
        first_key = next(iter(detail))
        inner = _summarise(detail[first_key])
        if first_key in {"detail", "non_field_errors"}:
            return inner
        return f"{first_key}: {inner}"
    return "Request failed."


def api_exception_handler(exc, context):
    """DRF `EXCEPTION_HANDLER`. Normalises everything into one envelope."""
    # Translate framework and ORM exceptions DRF does not handle natively.
    if isinstance(exc, DjangoValidationError):
        exc = APIException(
            detail=exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        )
        exc.status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, PermissionDenied):
        exc = APIException(detail=str(exc) or "Permission denied.")
        exc.status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, IntegrityError):
        # Almost always a unique constraint the service layer should have caught
        # first. Log it loudly but never leak the SQL to the client.
        logger.warning("IntegrityError surfaced to the API layer: %s", exc)
        exc = ConflictError()

    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled — let Django's 500 machinery log the traceback.
        return None

    if isinstance(exc, Http404):
        code = "not_found"
    else:
        code = getattr(exc, "default_code", None) or CODE_BY_STATUS.get(
            response.status_code, "error"
        )
        explicit = getattr(exc, "detail", None)
        if hasattr(explicit, "code") and explicit.code:
            code = explicit.code

    detail = response.data
    payload = {
        "error": {
            "code": code,
            "message": _summarise(detail),
            "details": detail if isinstance(detail, dict) else {},
        }
    }

    # Retry-After is what makes a 429 actionable rather than merely annoying.
    if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        wait = getattr(exc, "wait", None)
        if wait:
            payload["error"]["retry_after_seconds"] = int(wait)

    response.data = payload
    return response
