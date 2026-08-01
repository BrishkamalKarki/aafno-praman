"""
National identity handling — normalisation, peppered lookup hashing, and
encryption at rest.

This module exists because of one uncomfortable fact: a Nepali citizenship
number is not a secret, but it is not public either, and it has almost no
entropy. The format is district-structured and sequentially issued, so the
entire plausible keyspace is small enough to walk exhaustively on a laptop.

Three consequences shape everything below.

1. **A plain hash is not anonymisation.** ``sha256(citizenship_number)`` is
   reversible by exhaustive search in seconds. Every lookup value here is an
   HMAC under ``NATIONAL_ID_PEPPER``, a secret the database does not contain, so
   a stolen dump alone yields no identities.

2. **Nothing unsalted may reach the chain.** ``subject_binding`` (used by the
   canonical payload) mixes in 128 bits of per-record salt. Even a full pepper
   compromise then yields no cross-record correlation, because every record's
   binding is independently salted. A single global HMAC on-chain would let an
   attacker who ever obtained the pepper retroactively deanonymise the entire
   ledger — permanently, since anchors cannot be deleted.

3. **The raw number is needed rarely and stored accordingly.** Dispute
   resolution and any future government audit need the real value; nothing on a
   hot path does. It is held as Fernet ciphertext under the same envelope scheme
   that protects custodial issuer keys, and decrypted only at the point of use.

Rotation: ``hmac_version`` travels beside every stored hash. Changing the pepper
without it would mean a migration that cannot run incrementally, because there
is no way to tell a stale hash from a current one.
"""

from __future__ import annotations

import hmac
import re
import secrets
from hashlib import sha256

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

#: Every character that is not a digit is stripped before hashing. Citizenship
#: numbers are written inconsistently — "12-01-70-12345", "12/01/70/12345",
#: "12 01 70 12345" — and all three must resolve to one identity, or a citizen
#: ends up with two accounts and a degree in the one they cannot access.
_NON_DIGIT = re.compile(r"\D+")

#: Loose bounds only. A strict district/format check would reject the older and
#: hand-written variants still in circulation, and rejecting a real citizen's
#: real number is a worse failure than accepting an implausible one — the number
#: is attested by an issuer that holds the physical document, not by this regex.
MIN_DIGITS = 5
MAX_DIGITS = 20

#: Bytes of per-record salt for on-chain subject bindings. 128 bits is well past
#: any brute-force horizon and costs nothing: the salt is stored off-chain.
BINDING_SALT_BYTES = 16


class IdentityError(ValueError):
    """Raised when a national ID cannot be normalised, hashed or decrypted."""


def normalise_national_id(value: str | None) -> str:
    """
    Reduce a written citizenship number to its canonical digit string.

    Raises ``IdentityError`` rather than returning an empty string for invalid
    input: silently normalising junk to ``""`` would make every unparseable
    value collide into a single "identity" under the unique constraint.
    """
    if value is None:
        raise IdentityError("A citizenship number is required.")

    digits = _NON_DIGIT.sub("", str(value))
    if not digits:
        raise IdentityError("A citizenship number must contain digits.")
    if not MIN_DIGITS <= len(digits) <= MAX_DIGITS:
        raise IdentityError(
            f"A citizenship number must have between {MIN_DIGITS} and {MAX_DIGITS} "
            f"digits; got {len(digits)}."
        )
    return digits


def _pepper() -> bytes:
    pepper = getattr(settings, "NATIONAL_ID_PEPPER", "")
    if not pepper:
        raise IdentityError(
            "NATIONAL_ID_PEPPER is not set. Generate one with:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return pepper.encode() if isinstance(pepper, str) else pepper


def national_id_hmac(value: str) -> str:
    """
    Derive the lookup key for a national ID.

    This is the only value used to find an identity. It is deterministic (so it
    can carry a unique constraint) and irreversible without the pepper (so the
    column is not a citizen list).
    """
    normalised = normalise_national_id(value)
    return hmac.new(_pepper(), normalised.encode(), sha256).hexdigest()


def new_binding_salt() -> str:
    """Fresh per-record salt, hex-encoded for JSON and column storage."""
    return secrets.token_hex(BINDING_SALT_BYTES)


def subject_binding(value: str, salt: str) -> str:
    """
    Derive the salted subject binding that goes into the canonical payload.

    Binds a credential to a citizen cryptographically without disclosing which
    citizen. A verifier holding both the document and the claimed citizenship
    number can recompute this and confirm the match; someone holding only public
    chain data cannot work backwards to a person, because the salt never leaves
    the database.

    The salt is mixed as a separate HMAC round rather than concatenated into the
    message, so that a salt and an ID cannot be shuffled between each other to
    produce a colliding binding.
    """
    if not salt:
        raise IdentityError("A binding salt is required.")
    normalised = normalise_national_id(value)
    keyed = hmac.new(_pepper(), bytes.fromhex(salt), sha256).digest()
    return hmac.new(keyed, normalised.encode(), sha256).hexdigest()


def binding_matches(value: str, salt: str, expected: str) -> bool:
    """
    Constant-time comparison of a claimed identity against a record's binding.

    ``compare_digest`` matters here specifically: this runs on the verifier path
    where an attacker controls the input and can time the response, and a
    byte-wise early exit would leak the binding one character at a time.
    """
    if not (salt and expected):
        return False
    try:
        return hmac.compare_digest(subject_binding(value, salt), expected)
    except IdentityError:
        return False


def _fernet() -> Fernet:
    key = settings.KEY_ENCRYPTION_KEY
    if not key:
        raise IdentityError("KEY_ENCRYPTION_KEY is not set.")
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise IdentityError(
            "KEY_ENCRYPTION_KEY is not a valid Fernet key (32 url-safe base64 bytes)."
        ) from exc


def encrypt_national_id(value: str) -> bytes:
    """Encrypt the normalised national ID for at-rest storage."""
    return _fernet().encrypt(normalise_national_id(value).encode())


def decrypt_national_id(ciphertext: bytes | memoryview | None) -> str:
    """
    Decrypt a stored national ID.

    Callers must have a specific, auditable reason — dispute resolution or a
    registrar investigation. There is deliberately no serializer field, no admin
    display and no API response that calls this.
    """
    if not ciphertext:
        return ""
    if isinstance(ciphertext, memoryview):  # psycopg returns memoryview for bytea
        ciphertext = ciphertext.tobytes()
    try:
        return _fernet().decrypt(bytes(ciphertext)).decode()
    except InvalidToken as exc:
        raise IdentityError(
            "Cannot decrypt this national ID. KEY_ENCRYPTION_KEY has probably "
            "changed since it was stored."
        ) from exc


def mask_national_id(value: str | None, visible_suffix: int = 4) -> str:
    """
    Mask a national ID for display, keeping the tail for eyeball matching.

    Used where an issuer needs to confirm they are looking at the right person
    without the platform handing back the full number.
    """
    if not value:
        return ""
    text = str(value)
    if len(text) <= visible_suffix:
        return "•" * len(text)
    return "•" * (len(text) - visible_suffix) + text[-visible_suffix:]
