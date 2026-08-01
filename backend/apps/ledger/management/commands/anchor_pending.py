"""
Reconcile records stuck awaiting a ledger anchor.

Run on a schedule (cron, systemd timer, Render cron job):

    python manage.py anchor_pending --limit 100

This is what makes the "never lose a record" guarantee real. Issuance writes to
the database first and only then attempts the chain; when the node is
unreachable the record waits here rather than failing the issuer's request.
"""

from django.core.management.base import BaseCommand

from apps.ledger.services import retry_pending_anchors


class Command(BaseCommand):
    help = "Retry records left in PENDING_ANCHOR after a ledger outage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum anchors to process in one run (default: 50).",
        )

    def handle(self, *args, **options):
        summary = retry_pending_anchors(limit=options["limit"])

        self.stdout.write(
            f"checked={summary['checked']} "
            f"reconciled={summary['reconciled']} "
            f"anchored={summary['anchored']} "
            f"still_pending={summary['still_pending']} "
            f"failed={summary['failed']}"
        )

        if summary["failed"]:
            # Non-zero-ish signal for the operator: these need a human, because
            # they have exhausted their retry budget.
            self.stdout.write(
                self.style.WARNING(
                    f"{summary['failed']} anchor(s) exhausted their retries and need review."
                )
            )
        elif summary["checked"] == 0:
            self.stdout.write(self.style.SUCCESS("Nothing pending."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
