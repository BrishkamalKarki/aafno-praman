"""
Canonicalisation and hashing — the cryptographic core of the platform.

Proposal §6.1 promises that "any alteration to a document instantly fails the
check". That promise is only true if the issuer and the verifier, on different
machines, months apart, produce **byte-identical** input to the hash function.
Everything in this module exists to guarantee that.

The rules, and why each one is here:

1. **Sorted keys.** ``{"a":1,"b":2}`` and ``{"b":2,"a":1}`` are the same record.
   Python dict ordering must never leak into the hash.

2. **No insignificant whitespace.** ``json.dumps`` defaults to ``", "`` after
   commas; a different serialiser would not. Pinned to the compact form.

3. **NFC normalisation on every string.** The requirement that makes or breaks
   this in Nepal. "श्रेष्ठ" entered on one keyboard and the same name pasted
   from a PDF can be byte-different while rendering identically (composed vs
   decomposed Unicode). Without NFC, a perfectly genuine credential verifies as
   TAMPERED — and it would fail only for Devanagari names, which is the worst
   possible failure mode for a platform built for Nepal.

4. **No floating-point numbers, ever.** A CGPA of 3.7 is ``3.7000000000000002``
   in some serialisers and ``3.7`` in others. Every numeric value is converted to
   a fixed-precision decimal *string* before hashing, so the hash can never
   depend on IEEE-754 rounding or a language's float repr.

5. **Empty values are dropped.** ``None`` and ``""`` are omitted rather than
   serialised. This makes the format forward-compatible: adding an optional field
   that nobody fills in does not change the hash of existing records.

6. **Domain separation.** The canonical bytes are prefixed with a version tag, so
   a hash from this platform can never collide with a hash from another system
   that happens to canonicalise JSON the same way. The tag is part of the public
   contract with verifiers: changing it invalidates every QR code in circulation.

The output is a 64-character lowercase hex keccak256 digest — the same hash
function the Solidity contract uses, so the value the backend computes is the
value the chain stores, with no re-encoding in between.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from eth_utils import keccak

from apps.common.utils import normalise_text

# Decimal places used for every numeric field. Two is enough for CGPA (3.21) and
# percentage marks (78.50), and being fixed is more important than being generous.
NUMERIC_PRECISION = 2

# Bumped only alongside a migration plan for already-issued records. The version
# travels inside the payload so a verifier can tell which rules produced a hash.
#
# 1.1 adds the optional `subject_binding` field. Safe to change now because
# nothing is anchored on a public chain yet; after Sepolia it would invalidate
# every QR code in circulation and would need a dual-verification path instead.
PAYLOAD_SCHEMA_VERSION = "1.1"


class CanonicalisationError(ValueError):
    """Raised when a payload contains a value that cannot be canonicalised."""


def _canonical_value(value: Any, *, path: str = "") -> Any:
    """Recursively convert a value into its canonical, hashable form."""
    if value is None:
        return None

    if isinstance(value, bool):
        # Checked before int: bool is a subclass of int in Python.
        return value

    if isinstance(value, str):
        return normalise_text(value)

    if isinstance(value, (int, Decimal, float)):
        return _canonical_number(value, path=path)

    if isinstance(value, datetime):
        # Always UTC, always truncated to seconds. Hashing a local-time
        # representation would make the digest depend on the server's timezone —
        # a record issued in Kathmandu would fail verification on a UTC server.
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        return value.replace(microsecond=0, tzinfo=None).isoformat() + "Z"

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Mapping):
        return _canonical_mapping(value, path=path)

    if isinstance(value, (list, tuple)):
        # Order is preserved: a list of responsibilities is ordered data, and
        # sorting it would silently change the record's meaning.
        return [_canonical_value(item, path=f"{path}[{i}]") for i, item in enumerate(value)]

    raise CanonicalisationError(
        f"Unsupported type {type(value).__name__} at '{path or '<root>'}'. "
        "Convert it to a string, decimal, date, bool, list or mapping first."
    )


def _canonical_number(value: int | float | Decimal, *, path: str) -> str:
    """
    Render a number as a fixed-precision decimal string.

    Floats are accepted but immediately routed through ``Decimal(str(value))``,
    which uses Python's shortest-repr and so cannot smuggle a binary artefact
    such as 3.7000000000000002 into the hash.
    """
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CanonicalisationError(f"Invalid number at '{path}': {value!r}") from exc

    if not decimal_value.is_finite():
        raise CanonicalisationError(f"Non-finite number at '{path}': {value!r}")

    quantised = decimal_value.quantize(Decimal(1).scaleb(-NUMERIC_PRECISION))
    # normalize() would render 3.20 as 3.2 and 100 as 1E+2 — both unacceptable.
    return f"{quantised:.{NUMERIC_PRECISION}f}"


def _canonical_mapping(payload: Mapping, *, path: str = "") -> dict:
    """Canonicalise a mapping, dropping empty values and sorting keys."""
    result: dict[str, Any] = {}
    for raw_key in payload:
        if not isinstance(raw_key, str):
            raise CanonicalisationError(f"Non-string key {raw_key!r} at '{path or '<root>'}'.")
        key = normalise_text(raw_key)
        child_path = f"{path}.{key}" if path else key
        value = _canonical_value(payload[raw_key], path=child_path)

        # Rule 5 — drop empties so optional fields are forward-compatible.
        if value is None or value == "" or value == [] or value == {}:
            continue
        result[key] = value

    return dict(sorted(result.items(), key=lambda item: item[0]))


def canonical_dict(payload: Mapping) -> dict:
    """
    Return the canonicalised payload as a plain JSON-safe dict.

    This is the exact pre-image that gets hashed: dates already rendered as
    ISO-8601 strings, decimals as fixed-precision strings, keys sorted, empties
    dropped. Stored in ``CredentialRecord.canonical_payload`` so a verifier can
    be shown precisely what was hashed rather than a reconstruction of it — and
    so the column is serialisable, which a dict full of ``date`` objects is not.
    """
    return _canonical_mapping(payload)


def canonical_json(payload: Mapping) -> str:
    """
    Return the canonical JSON string for a payload.

    Exposed publicly because verifiers need to reproduce it independently, and
    because showing it side by side with the on-chain hash is the clearest way to
    demonstrate that the platform is not simply asserting "verified".
    """
    canonical = _canonical_mapping(payload)
    return json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(payload: Mapping) -> bytes:
    """Domain-tagged UTF-8 bytes that are fed to keccak256."""
    return f"{settings.CANONICAL_DOMAIN_TAG}\n{canonical_json(payload)}".encode()


def compute_record_hash(payload: Mapping) -> str:
    """
    keccak256 of the canonical payload, as 64 lowercase hex characters.

    No ``0x`` prefix and lowercase by construction: the database has a unique
    index on this column, and ``0xAB…`` versus ``ab…`` must never become two rows
    for one credential.
    """
    return keccak(canonical_bytes(payload)).hex()


def to_bytes32(record_hash: str) -> bytes:
    """Convert a stored hex hash into the 32 raw bytes the contract expects."""
    cleaned = record_hash[2:] if record_hash.startswith("0x") else record_hash
    if len(cleaned) != 64:
        raise CanonicalisationError(f"Expected a 64-character hex hash, got {len(cleaned)}.")
    return bytes.fromhex(cleaned)


def from_bytes32(value: bytes | str) -> str:
    """Convert a bytes32 from the chain back into the stored hex form."""
    if isinstance(value, str):
        return value[2:].lower() if value.startswith("0x") else value.lower()
    return value.hex()
