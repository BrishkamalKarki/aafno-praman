"""Small shared helpers with no app-specific dependencies."""

import hashlib
import secrets
import unicodedata

from django.conf import settings


def hash_ip(ip_address: str | None) -> str:
    """
    Hash a client IP for logging.

    Verification logs need per-client abuse tracing and monthly quota counting,
    but a public credential-checking service that stores raw IPs next to
    credential hashes is building a record of who investigated whose degree.
    Keyed with SECRET_KEY so the hashes are not reversible via a rainbow table
    of the IPv4 space.
    """
    if not ip_address:
        return ""
    digest = hashlib.sha256(f"{settings.SECRET_KEY}:{ip_address}".encode())
    return digest.hexdigest()


def client_ip(request) -> str:
    """
    Best-effort client IP.

    `X-Forwarded-For` is client-controlled and trusted only because deployment
    puts a proxy in front that overwrites it. The left-most entry is the
    original client when that holds.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def sha256_file(file_obj) -> str:
    """Stream a hash over an uploaded file without loading it into memory."""
    digest = hashlib.sha256()
    position = file_obj.tell()
    file_obj.seek(0)
    for chunk in iter(lambda: file_obj.read(64 * 1024), b""):
        digest.update(chunk)
    file_obj.seek(position)
    return digest.hexdigest()


def normalise_text(value: str | None) -> str:
    """
    NFC-normalise and collapse whitespace.

    Non-negotiable for Nepali data: 'श्रेष्ठ' typed on one keyboard layout and
    the same name pasted from a PDF can be byte-different while looking
    identical (NFC vs NFD). Without normalisation those hash differently and a
    genuine credential verifies as TAMPERED.
    """
    if value is None:
        return ""
    return " ".join(unicodedata.normalize("NFC", str(value)).split())


def generate_token(length: int = 32) -> str:
    """URL-safe random token for share links."""
    return secrets.token_urlsafe(length)


def mask_identifier(value: str | None, visible_suffix: int = 3) -> str:
    """
    Mask a registration or national ID, keeping the tail for eyeball matching.

    Implements the 'hiding sensitive ID numbers' control in proposal §6.3: a
    recruiter can confirm the number they were given ends in the same digits
    without the platform handing out the full identifier.
    """
    if not value:
        return ""
    text = str(value)
    if len(text) <= visible_suffix:
        return "•" * len(text)
    return "•" * (len(text) - visible_suffix) + text[-visible_suffix:]
