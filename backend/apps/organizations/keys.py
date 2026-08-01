"""
Custodial signing-key management.

The platform generates and holds an EVM keypair per approved issuer. See the
docstring on ``IssuerKey`` for why, and ``docs/SECURITY.md`` for the honest
account of what that centralisation costs.

Envelope encryption: private keys are stored as Fernet ciphertext under
``KEY_ENCRYPTION_KEY``, which lives in the environment and never in the
database. A stolen database dump alone therefore yields no signing capability —
the attacker needs the application environment too.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from eth_account import Account

from .models import IssuerKey, Organization

logger = logging.getLogger(__name__)


class KeyManagementError(RuntimeError):
    """Raised when a signing key cannot be created, decrypted or used."""


def _fernet() -> Fernet:
    key = settings.KEY_ENCRYPTION_KEY
    if not key:
        raise KeyManagementError(
            "KEY_ENCRYPTION_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise KeyManagementError(
            "KEY_ENCRYPTION_KEY is not a valid Fernet key (32 url-safe base64 bytes)."
        ) from exc


@transaction.atomic
def create_issuer_key(organization: Organization) -> IssuerKey:
    """
    Generate and store a signing keypair for an organisation.

    Idempotent: an organisation that already has a key keeps it. Rotating a key
    is a deliberate, separate operation, because the old address is what every
    already-anchored record was signed by — silently replacing it would orphan
    the organisation's entire issuance history.
    """
    existing = IssuerKey.objects.select_for_update().filter(organization=organization).first()
    if existing is not None:
        return existing

    account = Account.create()
    issuer_key = IssuerKey.objects.create(
        organization=organization,
        address=account.address,
        encrypted_private_key=_fernet().encrypt(account.key.hex().encode()),
        key_version=1,
    )
    # Logged at info with the public address only — never the private key, and
    # never the ciphertext.
    logger.info(
        "Generated signing key for organisation %s (address=%s)",
        organization.slug,
        account.address,
    )
    return issuer_key


def load_private_key(issuer_key: IssuerKey) -> str:
    """
    Decrypt an issuer's private key for immediate use.

    The plaintext should live no longer than the transaction that needs it: take
    it, sign, drop the reference. It is deliberately returned rather than cached.
    """
    ciphertext = issuer_key.encrypted_private_key
    if isinstance(ciphertext, memoryview):  # psycopg returns memoryview for bytea
        ciphertext = ciphertext.tobytes()
    try:
        plaintext = _fernet().decrypt(bytes(ciphertext)).decode()
    except InvalidToken as exc:
        raise KeyManagementError(
            f"Cannot decrypt the signing key for {issuer_key.organization.slug}. "
            "KEY_ENCRYPTION_KEY has probably changed since the key was created."
        ) from exc

    # eth-account accepts either form; normalise so callers never have to care.
    return plaintext if plaintext.startswith("0x") else f"0x{plaintext}"


def get_signer(organization: Organization) -> tuple[str, str]:
    """
    Return ``(address, private_key)`` for an organisation, marking the key used.

    ``last_used_at`` is maintained because an issuer key that suddenly starts
    signing at 3 a.m. after months of business-hours use is the signal that a
    compromise has happened.
    """
    issuer_key = IssuerKey.objects.filter(organization=organization).first()
    if issuer_key is None:
        raise KeyManagementError(
            f"Organisation {organization.slug} has no signing key. "
            "It must be approved by the registrar first."
        )

    private_key = load_private_key(issuer_key)
    IssuerKey.objects.filter(pk=issuer_key.pk).update(last_used_at=timezone.now())
    return issuer_key.address, private_key
