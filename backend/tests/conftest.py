"""
Shared test fixtures.

## A known limitation of this suite

Tests run on in-memory SQLite for speed. SQLite **silently ignores**
``select_for_update``, so no test here can catch a row-locking bug — and one got
through exactly that way: ``FOR UPDATE`` combined with ``select_related`` across
a nullable foreign key emits a LEFT OUTER JOIN, which PostgreSQL rejects
("FOR UPDATE cannot be applied to the nullable side of an outer join") and
SQLite accepts. The suite passed; production would have 500'd on every
credential confirmation.

Until there is a PostgreSQL CI job, any change touching ``select_for_update``
must be exercised against a real Postgres database before it is called done.

Deliberately thin. Factories that hide which fields matter make a failing test
harder to read than the code it is testing, so fixtures here build only what
every suite needs and leave the interesting values at the call site.
"""

import pytest

from apps.accounts.services import get_or_create_account
from apps.organizations.models import (
    Organization,
    OrganizationKind,
    OrganizationStatus,
)

#: A real Nepali-format citizenship number shape. Not a real number.
NATIONAL_ID = "12-01-70-98765"


@pytest.fixture(autouse=True)
def _identity_secrets(settings):
    """
    Pin the identity secrets for every test.

    Fixed rather than random so a hash asserted in one test is the same hash in
    another, and so a failure is reproducible from the test file alone.
    """
    settings.NATIONAL_ID_PEPPER = "test-pepper-do-not-use-in-any-real-environment"
    settings.KEY_ENCRYPTION_KEY = "MWhSDm5bE3bsCKbMEmMkGf_GhqA_QRLwi7Dlppel3yo="
    settings.NATIONAL_ID_HMAC_VERSION = 1


@pytest.fixture
def institution(db):
    return Organization.objects.create(
        kind=OrganizationKind.INSTITUTION,
        legal_name="Tribhuvan University",
        slug="tribhuvan-university",
        registration_number="UGC-001",
        contact_email="registrar@tu.edu.np",
        status=OrganizationStatus.APPROVED,
        chain_address="0x" + "11" * 20,
    )


@pytest.fixture
def employer(db):
    return Organization.objects.create(
        kind=OrganizationKind.EMPLOYER,
        legal_name="Leapfrog Technology",
        slug="leapfrog",
        registration_number="PAN-30188",
        contact_email="hr@leapfrog.com.np",
        status=OrganizationStatus.APPROVED,
        chain_address="0x" + "22" * 20,
    )


@pytest.fixture
def holder(db):
    """An email-only account, as issuance to an unknown address creates it."""
    profile, _ = get_or_create_account(email="sita@example.com", full_name="Sita Sharma")
    return profile


@pytest.fixture
def stub_ledger(monkeypatch):
    """
    A ledger client whose issuer-registration writes succeed.

    Needed because ``approve_organization`` is deliberately **chain-first and
    atomic**: an organisation marked APPROVED in the database but absent from
    the contract would fail at its first issuance with an opaque revert, so the
    service refuses to approve at all when the node is unreachable. The test
    settings disable the chain, which means approval correctly fails there —
    testing that path requires standing a working ledger in, not weakening the
    service.

    Everything not explicitly stubbed **delegates to the real disabled client**
    rather than returning a convenient fake. That keeps the surface honest: gas
    top-ups and verification reads still exercise their genuine "ledger
    unreachable" degradation paths, so a test cannot accidentally pass because
    the stub was more capable than production.
    """
    from apps.ledger.client import TxResult
    from apps.ledger.client import get_ledger_client as real_get_client

    real = real_get_client()

    class _StubLedger:
        def approve_issuer(self, address, kind, name):
            return TxResult(tx_hash="0x" + "ab" * 32, block_number=1, chain_id=31337)

        def suspend_issuer(self, address, reason):
            return TxResult(tx_hash="0x" + "cd" * 32, block_number=2, chain_id=31337)

        def reinstate_issuer(self, address):
            return TxResult(tx_hash="0x" + "ef" * 32, block_number=3, chain_id=31337)

        def __getattr__(self, name):
            return getattr(real, name)

    stub = _StubLedger()
    for module in ("apps.organizations.services", "apps.ledger.services"):
        monkeypatch.setattr(f"{module}.get_ledger_client", lambda: stub, raising=False)
    return stub
