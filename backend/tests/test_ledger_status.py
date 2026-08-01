"""
The status endpoint has to survive the thing it reports on.

`/ledger/status/` is what the frontend's ledger banner polls to decide whether
to warn that anchoring is paused. It is the one endpoint that must keep
answering when the chain does not — an endpoint that 500s precisely when the
ledger is broken tells every dashboard "request failed" instead of "the chain is
down, credentials are queued", which are very different messages to show a
university registrar mid-graduation-batch.

`Web3LedgerClient.health()` already handles a node that is configured but
unreachable. What escaped was the earlier failure: the client could not be
*constructed* — no `CHAIN_CONTRACT_ADDRESS`, an unparseable RPC URL, a missing
ABI file. Switching the deployment to Sepolia surfaced it, because the contract
address is empty until someone deploys.
"""

import pytest
from rest_framework.test import APIClient

from apps.ledger.client import LedgerUnavailableError


@pytest.fixture
def anonymous():
    return APIClient()


@pytest.mark.django_db
class TestStatusWhenTheLedgerIsUnusable:
    def test_an_unconstructable_client_reports_unhealthy_rather_than_500(
        self, anonymous, monkeypatch
    ):
        def explode():
            raise LedgerUnavailableError("CHAIN_CONTRACT_ADDRESS is not set.")

        # Patched on the view module, not on `apps.ledger.client`. The view did
        # `from .client import get_ledger_client`, so it holds its own reference
        # — and replacing the original would also strip the `lru_cache` wrapper
        # that `reset_ledger_client()` needs, breaking teardown for every test
        # after this one.
        monkeypatch.setattr("apps.ledger.views.get_ledger_client", explode)

        response = anonymous.get("/api/v1/ledger/status/")

        assert response.status_code == 200
        assert response.data["ledger"]["ok"] is False
        assert "CHAIN_CONTRACT_ADDRESS" in response.data["ledger"]["error"]

    def test_the_local_anchor_counts_are_still_reported(self, anonymous, monkeypatch):
        """
        The database half of the answer does not depend on the chain, and it is
        the half that tells an operator how much work is queued waiting for it.
        """

        def explode():
            raise LedgerUnavailableError("no contract")

        monkeypatch.setattr("apps.ledger.views.get_ledger_client", explode)

        response = anonymous.get("/api/v1/ledger/status/")

        assert response.status_code == 200
        assert set(response.data["local"]) == {
            "confirmed_anchors",
            "pending_anchors",
            "failed_anchors",
        }

    def test_the_endpoint_stays_anonymous(self, anonymous):
        """
        Public on purpose: a platform claiming to be blockchain-backed should
        let anyone confirm which chain and which contract, without an account.
        Gating it behind auth would make the transparency claim unauditable.
        """
        assert anonymous.get("/api/v1/ledger/status/").status_code == 200
