"""
Detect — and explain how to repair — drift between PostgreSQL and the chain.

The two stores can disagree in exactly two ways, and they need opposite
responses:

* **The database is ahead.** A record is ISSUED locally but has no anchor on
  chain, or an APPROVED organisation is not a registered issuer. On a local
  Hardhat node this is almost always because the node was restarted: its state
  is in memory, so every issuer and anchor vanishes while PostgreSQL keeps
  every row. Re-anchoring is safe and is what `--repair` does.

* **The chain is ahead.** An anchor exists for a hash the database has no row
  for. This is *not* repairable here and must never be "fixed" by deleting the
  anchor: the ledger is append-only by design, and a hash with no local record
  is evidence worth investigating, not noise to clear.

Exit code is non-zero when drift is found, so this can gate a deploy or run as
a cron health check.
"""

from django.core.management.base import BaseCommand

from apps.credentials.models import CredentialRecord, RecordStatus
from apps.ledger.client import LedgerError, LedgerUnavailableError, get_ledger_client
from apps.ledger.services import retry_pending_anchors
from apps.organizations.models import Organization, OrganizationStatus


class Command(BaseCommand):
    help = "Report (and optionally repair) drift between the database and the ledger."

    def add_arguments(self, parser):
        parser.add_argument(
            "--repair",
            action="store_true",
            help="Re-anchor records the chain is missing. Never deletes anything.",
        )

    def handle(self, *args, **options):
        try:
            client = get_ledger_client()
            health = client.health()
        except LedgerError as exc:
            self.stderr.write(self.style.ERROR(f"Ledger unavailable: {exc}"))
            raise SystemExit(2)

        if not health.get("ok"):
            self.stderr.write(
                self.style.ERROR(
                    f"Ledger unreachable: {health.get('error', health.get('reason', 'unknown'))}\n"
                    "Start it with `npm run node` in contracts/, then re-run."
                )
            )
            raise SystemExit(2)

        self.stdout.write(
            f"ledger: chain_id={health['chain_id']} block={health['block_number']} "
            f"anchors_on_chain={health['anchor_count']}"
        )

        stale_issuers = self._check_issuers(client)
        missing_anchors = self._check_anchors(client)

        if options["repair"] and missing_anchors:
            self._repair(missing_anchors, stale_issuers)
            missing_anchors = self._check_anchors(client, quiet=True)

        self.stdout.write("")
        if not stale_issuers and not missing_anchors:
            self.stdout.write(self.style.SUCCESS("IN SYNC — database and ledger agree."))
            return

        self.stdout.write(self.style.ERROR("DRIFT DETECTED"))
        if stale_issuers:
            self.stdout.write(
                f"  {len(stale_issuers)} approved organisation(s) are not issuers on this chain."
            )
        if missing_anchors:
            self.stdout.write(f"  {len(missing_anchors)} issued record(s) are not anchored.")

        # Re-approval regenerates signing keys and is destructive to demo data,
        # so it is never done implicitly — the operator gets the command instead.
        self.stdout.write("")
        self.stdout.write("Recovery:")
        if stale_issuers:
            self.stdout.write(
                "  The chain was reset. Rebuild the demo world against it:\n"
                "    python manage.py seed_demo --reset && python manage.py create_roles"
            )
        elif missing_anchors:
            self.stdout.write("    python manage.py chain_sync --repair")
        raise SystemExit(1)

    # ---------------------------------------------------------------- checks

    def _check_issuers(self, client) -> list:
        stale = []
        for org in Organization.objects.filter(status=OrganizationStatus.APPROVED):
            if not org.chain_address:
                stale.append(org)
                continue
            try:
                if not client.can_anchor(org.chain_address):
                    stale.append(org)
            except LedgerUnavailableError:
                stale.append(org)

        for org in stale:
            self.stdout.write(
                self.style.WARNING(
                    f"  issuer drift: {org.slug} is APPROVED in the database but "
                    f"cannot anchor on chain ({org.chain_address or 'no address'})"
                )
            )
        return stale

    def _check_anchors(self, client, *, quiet: bool = False) -> list:
        missing = []
        records = CredentialRecord.objects.filter(
            status__in=[RecordStatus.ISSUED, RecordStatus.REVOKED, RecordStatus.SUPERSEDED]
        ).exclude(record_hash="")

        for record in records:
            try:
                if not client.verify(record.record_hash).exists:
                    missing.append(record)
            except LedgerUnavailableError:
                missing.append(record)

        if not quiet:
            for record in missing:
                self.stdout.write(
                    self.style.WARNING(
                        f"  anchor drift: {record.pk} ({record.status}) "
                        f"hash {record.record_hash[:16]}… is absent from the ledger"
                    )
                )
        return missing

    # ---------------------------------------------------------------- repair

    def _repair(self, missing_anchors: list, stale_issuers: list) -> None:
        if stale_issuers:
            self.stdout.write(
                self.style.WARNING(
                    "\n  Skipping repair: the issuing organisations are not registered on "
                    "this chain, so re-anchoring would revert. Re-seed instead."
                )
            )
            return

        self.stdout.write(f"\n  Re-anchoring {len(missing_anchors)} record(s)…")
        # Reset to PENDING_ANCHOR and let the existing retry path do the work,
        # rather than duplicating the nonce, gas and confirmation handling that
        # `retry_pending_anchors` already gets right.
        for record in missing_anchors:
            record.status = RecordStatus.PENDING_ANCHOR
            record.save(update_fields=["status"])

        summary = retry_pending_anchors(limit=len(missing_anchors))
        self.stdout.write(
            f"  checked={summary['checked']} anchored={summary['anchored']} "
            f"still_pending={summary['still_pending']} failed={summary['failed']}"
        )
