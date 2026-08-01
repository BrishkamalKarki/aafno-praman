"""Lapse credential offers nobody answered."""

from django.core.management.base import BaseCommand

from apps.credentials.confirmations import expire_stale_offers


class Command(BaseCommand):
    help = "Expire credential offers whose confirmation window has closed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Maximum offers to expire in one run. Bounds the transaction size.",
        )

    def handle(self, *args, **options):
        # Run on a schedule. Without it an unanswered offer holds the dedupe key
        # for its credential forever, so an institution that mistyped a
        # graduate's address could never re-issue to the correct one.
        count = expire_stale_offers(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Expired {count} unanswered offer(s)."))
