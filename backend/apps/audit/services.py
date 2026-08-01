"""Audit recording helper."""

from __future__ import annotations

import logging
from typing import Any

from apps.common.utils import client_ip, hash_ip

from .models import AuditEvent

logger = logging.getLogger(__name__)


def record_event(
    action: str,
    *,
    actor=None,
    organization=None,
    obj: Any = None,
    metadata: dict | None = None,
    request=None,
) -> AuditEvent | None:
    """
    Write one audit event.

    Never raises. An audit failure must not roll back the business operation it
    was describing — losing a log line is bad, but failing a graduate's degree
    issuance because the audit insert hit a constraint would be worse. Failures
    are logged at ``exception`` level so they surface in monitoring instead of
    vanishing.
    """
    try:
        return AuditEvent.objects.create(
            action=action,
            actor=actor if getattr(actor, "pk", None) else None,
            actor_label=getattr(actor, "email", "") or "",
            organization=organization,
            object_type=obj.__class__.__name__ if obj is not None else "",
            object_id=str(getattr(obj, "pk", "")) if obj is not None else "",
            metadata=_sanitise(metadata or {}),
            client_ip_hash=hash_ip(client_ip(request)) if request is not None else "",
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to record audit event %s", action)
        return None


#: Keys whose values must never reach the audit log even by accident.
_FORBIDDEN_KEYS = {
    "password",
    "private_key",
    "encrypted_private_key",
    "signer_key",
    "token",
    "passphrase",
    "national_id",
    "authorization",
}


def _sanitise(metadata: dict) -> dict:
    """
    Strip anything sensitive before persisting.

    Audit metadata is free-form, which makes it the most likely place for a
    secret to be logged by accident during a late-night feature addition. Keys
    are filtered by name here, once, rather than trusting every call site.
    """
    cleaned = {}
    for key, value in metadata.items():
        if key.lower() in _FORBIDDEN_KEYS:
            cleaned[key] = "[redacted]"
        elif isinstance(value, dict):
            cleaned[key] = _sanitise(value)
        else:
            cleaned[key] = value
    return cleaned
