"""Reusable field and upload validators."""

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible


@deconstructible
class UploadValidator:
    """
    Validate an uploaded credential document.

    Checks extension, declared content type and real size. It deliberately does
    *not* claim to prove the file is a safe PDF — that needs content sniffing —
    so uploads are stored private and served through signed URLs rather than
    rendered inline from a trusted origin.
    """

    ALLOWED_CONTENT_TYPES = {
        "application/pdf",
        "image/png",
        "image/jpeg",
    }

    def __init__(self, max_bytes: int | None = None, extensions: list[str] | None = None):
        self.max_bytes = max_bytes or settings.MAX_UPLOAD_SIZE_BYTES
        self.extensions = extensions or settings.ALLOWED_UPLOAD_EXTENSIONS

    def __call__(self, file_obj):
        suffix = Path(file_obj.name).suffix.lower()
        if suffix not in self.extensions:
            raise ValidationError(
                f"Unsupported file type '{suffix}'. Allowed: {', '.join(self.extensions)}."
            )

        if file_obj.size > self.max_bytes:
            limit_mb = self.max_bytes / (1024 * 1024)
            raise ValidationError(f"File is larger than the {limit_mb:.0f} MB limit.")

        content_type = getattr(file_obj, "content_type", None)
        if content_type and content_type not in self.ALLOWED_CONTENT_TYPES:
            raise ValidationError(f"Unsupported content type '{content_type}'.")

    def __eq__(self, other):
        return (
            isinstance(other, UploadValidator)
            and self.max_bytes == other.max_bytes
            and self.extensions == other.extensions
        )


def validate_eth_address(value: str) -> None:
    """Validate a checksummed or lowercase 0x-prefixed EVM address."""
    if not isinstance(value, str) or not value.startswith("0x") or len(value) != 42:
        raise ValidationError("Must be a 0x-prefixed 20-byte hex address.")
    try:
        int(value[2:], 16)
    except ValueError as exc:
        raise ValidationError("Address contains non-hexadecimal characters.") from exc


def validate_record_hash(value: str) -> None:
    """
    Validate a 64-character lowercase hex hash (keccak256, no 0x prefix).

    Storing hashes without the prefix and in one fixed case keeps the unique
    index meaningful — '0xAB…' and 'ab…' must never be two rows for one record.
    """
    if not isinstance(value, str) or len(value) != 64:
        raise ValidationError("Record hash must be 64 hex characters.")
    if value != value.lower():
        raise ValidationError("Record hash must be lowercase.")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValidationError("Record hash contains non-hexadecimal characters.") from exc
