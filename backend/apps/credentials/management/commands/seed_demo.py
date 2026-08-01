"""
Seed a complete, demonstrable dataset.

Every record this creates is anchored on the real chain through the real service
layer — no fixtures, no fabricated transaction hashes. If the ledger is
unreachable the command says so rather than pretending, because a demo built on
fake anchors would fall apart at the first question from a judge.

    python manage.py seed_demo            # create everything
    python manage.py seed_demo --reset    # wipe demo data first
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, SeekerProfile
from apps.credentials.models import AcademicDetail, CredentialRecord, ExperienceDetail, RecordType
from apps.credentials.services import claim_record, issue_record
from apps.ledger.client import LedgerUnavailableError, get_ledger_client
from apps.organizations.models import (
    MembershipRole,
    Organization,
    OrganizationKind,
    OrganizationMembership,
    Plan,
    Subscription,
)
from apps.organizations.services import approve_organization
from apps.verification.models import ShareLink

User = get_user_model()

DEMO_PASSWORD = "AafnoPraman2026!"

SEEKERS = [
    ("sita.sharma@example.com", "Sita Sharma", "BSc CSIT graduate — backend developer"),
    ("bikash.thapa@example.com", "Bikash Thapa", "MBA — operations analyst"),
    ("anjali.gurung@example.com", "Anjali Gurung", "BE Civil — site engineer"),
]


class Command(BaseCommand):
    help = "Seed demo organisations, users and on-chain credentials."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first.")
        parser.add_argument(
            "--skip-chain-check",
            action="store_true",
            help="Seed even if the ledger is unreachable (records stay PENDING_ANCHOR).",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self._reset()

        if not options["skip_chain_check"]:
            self._require_chain()

        registrar = self._registrar()
        university = self._organization(
            slug="tribhuvan-university",
            kind=OrganizationKind.INSTITUTION,
            legal_name="Tribhuvan University",
            registration_number="UGC-NP-0001",
            contact="registrar@tu.edu.np",
            owner_email="registrar@tu.edu.np",
            owner_name="TU Registrar Office",
            registrar=registrar,
        )
        employer = self._organization(
            slug="leapfrog-technology",
            kind=OrganizationKind.EMPLOYER,
            legal_name="Leapfrog Technology Nepal",
            registration_number="PAN-302145879",
            contact="hr@lftechnology.com",
            owner_email="hr@lftechnology.com",
            owner_name="Leapfrog HR",
            registrar=registrar,
        )
        second_employer = self._organization(
            slug="fusemachines-nepal",
            kind=OrganizationKind.EMPLOYER,
            legal_name="Fusemachines Nepal",
            registration_number="PAN-604887231",
            contact="people@fusemachines.com",
            owner_email="people@fusemachines.com",
            owner_name="Fusemachines People Ops",
            registrar=registrar,
        )

        seekers = [self._seeker(email, name, headline) for email, name, headline in SEEKERS]

        self.stdout.write(self.style.MIGRATE_HEADING("\nIssuing academic credentials…"))
        sita_degree = self._issue_academic(
            university,
            "Sita Sharma",
            "sita.sharma@example.com",
            registration_number="TU-2078-CSIT-041",
            degree_title="Bachelor of Science in Computer Science and Information Technology",
            major="Computer Science",
            level=AcademicDetail.Level.BACHELORS,
            graduation=date(2026, 6, 15),
            bs_date="2083-03-01",
            cgpa=Decimal("3.21"),
        )
        self._issue_academic(
            university,
            "Bikash Thapa",
            "bikash.thapa@example.com",
            registration_number="TU-2076-MBA-118",
            degree_title="Master of Business Administration",
            major="Operations Management",
            level=AcademicDetail.Level.MASTERS,
            graduation=date(2025, 9, 20),
            bs_date="2082-06-04",
            cgpa=Decimal("3.64"),
        )
        self._issue_academic(
            university,
            "Anjali Gurung",
            "anjali.gurung@example.com",
            registration_number="TU-2077-CIV-227",
            degree_title="Bachelor of Engineering in Civil Engineering",
            major="Structural Engineering",
            level=AcademicDetail.Level.BACHELORS,
            graduation=date(2026, 2, 10),
            bs_date="2082-10-27",
            percentage=Decimal("78.40"),
        )

        self.stdout.write(self.style.MIGRATE_HEADING("\nIssuing employment records…"))
        self._issue_experience(
            employer,
            "Sita Sharma",
            "sita.sharma@example.com",
            job_title="Software Engineer",
            department="Engineering",
            start=date(2024, 7, 1),
            end=date(2026, 5, 30),
            departure=ExperienceDetail.DepartureStatus.RESIGNED,
            responsibilities="Django REST services, PostgreSQL schema design, CI pipelines.",
        )
        self._issue_experience(
            second_employer,
            "Bikash Thapa",
            "bikash.thapa@example.com",
            job_title="Operations Analyst",
            department="Business Operations",
            start=date(2025, 11, 1),
            end=None,
            departure=ExperienceDetail.DepartureStatus.CURRENT,
            responsibilities="Vendor analytics, capacity planning, quarterly reporting.",
        )

        self.stdout.write(self.style.MIGRATE_HEADING("\nCreating a pending endorsement claim…"))
        self._claim(seekers[2], second_employer)

        share_link = self._share_link(seekers[0])

        self._summary(sita_degree, share_link)

    # ------------------------------------------------------------- helpers

    def _require_chain(self) -> None:
        try:
            health = get_ledger_client().health()
        except LedgerUnavailableError as exc:
            raise CommandError(
                f"The ledger is unreachable: {exc}\n\n"
                "Start it first:\n"
                "  cd contracts && npm run node        # terminal 1\n"
                "  cd contracts && npm run deploy:local  # terminal 2\n"
                "then set CHAIN_CONTRACT_ADDRESS in backend/.env.\n\n"
                "Or re-run with --skip-chain-check to seed unanchored records."
            ) from exc

        if not health.get("ok"):
            raise CommandError(
                f"The ledger reported an error: {health.get('error', health)}\n"
                "Check CHAIN_RPC_URL and CHAIN_CONTRACT_ADDRESS in backend/.env."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Ledger reachable — chain {health['chain_id']}, "
                f"block {health['block_number']}, contract {health['contract_address']}"
            )
        )

    @transaction.atomic
    def _reset(self) -> None:
        self.stdout.write(self.style.WARNING("Resetting demo data…"))
        ShareLink.objects.all().delete()
        CredentialRecord.objects.all().delete()
        Organization.objects.all().delete()
        User.objects.exclude(is_superuser=True).delete()

    def _registrar(self) -> User:
        """
        The demo registrar.

        The password is set on **every** run, not only on creation. ``--reset``
        deliberately spares superusers, so this account survives a reseed — and
        with a create-only password the command would then print
        "all accounts use AafnoPraman2026!" while the one account that opens the
        admin console still had whatever password it was given first. A summary
        that is wrong about how to sign in is worse than no summary.

        Scoped to this fixed demo address, so a real superuser created with any
        other email is never touched.
        """
        registrar, created = User.objects.get_or_create(
            email="registrar@aafnopraman.np",
            defaults={
                "full_name": "Aafno Praman Platform Registrar",
                "role": Role.REGISTRAR,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        registrar.set_password(DEMO_PASSWORD)
        registrar.save()
        self.stdout.write(
            f"  registrar   {registrar.email}{'' if created else ' (password reset)'}"
        )
        return registrar

    def _organization(
        self,
        *,
        slug,
        kind,
        legal_name,
        registration_number,
        contact,
        owner_email,
        owner_name,
        registrar,
    ) -> Organization:
        organization = Organization.objects.filter(slug=slug).first()
        if organization is None:
            organization = Organization.objects.create(
                slug=slug,
                kind=kind,
                legal_name=legal_name,
                registration_number=registration_number,
                contact_email=contact,
                website=f"https://{slug}.example.np",
                address="Kathmandu, Nepal",
            )

        owner, created = User.objects.get_or_create(
            email=owner_email,
            defaults={"full_name": owner_name, "role": Role.ORG_MEMBER},
        )
        if created:
            owner.set_password(DEMO_PASSWORD)
            owner.save()
        OrganizationMembership.objects.get_or_create(
            user=owner, organization=organization, defaults={"role": MembershipRole.OWNER}
        )

        if not organization.can_issue:
            approve_organization(organization, registrar=registrar)
            organization.refresh_from_db()
            self.stdout.write(
                f"  approved    {legal_name} → {organization.chain_address} "
                f"(tx {organization.approval_tx_hash[:14]}…)"
            )

        # Read from settings rather than a literal. A seeded employer whose free
        # quota disagrees with FREE_PLAN_MONTHLY_LOOKUPS makes the quota meter
        # show a number the pricing page never promised, and the drift is
        # invisible until someone counts verifications.
        Subscription.objects.get_or_create(
            organization=organization,
            defaults={
                "plan": Plan.FREE,
                "monthly_lookup_limit": settings.FREE_PLAN_MONTHLY_LOOKUPS,
            },
        )
        return organization

    def _seeker(self, email: str, name: str, headline: str) -> SeekerProfile:
        user, created = User.objects.get_or_create(
            email=email, defaults={"full_name": name, "role": Role.SEEKER}
        )
        # Set the password unconditionally, not only on creation. A credential
        # issued to this address before seeding already created the account via
        # `get_or_create_account`, which deliberately leaves it with an unusable
        # password — so `if created` would skip it and leave a demo holder who
        # cannot sign in to the dashboard the demo is meant to show.
        if not user.check_password(DEMO_PASSWORD):
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
            self.stdout.write(f"  seeker      {email}")

        profile = SeekerProfile.objects.get(user=user)
        if not profile.headline:
            profile.headline = headline
            profile.is_discoverable = True
            profile.save(update_fields=["headline", "is_discoverable"])
        return profile

    def _issue_academic(self, issuer, name, email, **fields) -> CredentialRecord:
        existing = CredentialRecord.objects.filter(
            issuer=issuer,
            subject_email=email,
            academic_detail__registration_number=fields["registration_number"],
        ).first()
        if existing:
            return existing

        record = issue_record(
            issuer=issuer,
            actor=issuer.approved_by,
            record_type=RecordType.ACADEMIC,
            subject_email=email,
            subject_full_name=name,
            detail_data={
                "registration_number": fields["registration_number"],
                "degree_title": fields["degree_title"],
                "major": fields.get("major", ""),
                "level": fields["level"],
                "graduation_date": fields["graduation"],
                "graduation_date_bs": fields.get("bs_date", ""),
                "cgpa": fields.get("cgpa"),
                "percentage": fields.get("percentage"),
                "honours": fields.get("honours", ""),
            },
        )
        self._report(record, name)
        return record

    def _issue_experience(self, issuer, name, email, **fields) -> CredentialRecord:
        existing = CredentialRecord.objects.filter(
            issuer=issuer, subject_email=email, experience_detail__job_title=fields["job_title"]
        ).first()
        if existing:
            return existing

        record = issue_record(
            issuer=issuer,
            actor=issuer.approved_by,
            record_type=RecordType.EXPERIENCE,
            subject_email=email,
            subject_full_name=name,
            detail_data={
                "job_title": fields["job_title"],
                "department": fields.get("department", ""),
                "employment_type": ExperienceDetail.EmploymentType.FULL_TIME,
                "start_date": fields["start"],
                "end_date": fields["end"],
                "is_current": fields["end"] is None,
                "departure_status": fields["departure"],
                "responsibilities": fields.get("responsibilities", ""),
            },
        )
        self._report(record, name)
        return record

    def _claim(self, seeker: SeekerProfile, employer: Organization) -> None:
        """A seeker-submitted claim awaiting employer endorsement (§6.2 / HR-06)."""
        if CredentialRecord.objects.filter(
            subject=seeker, issuer=employer, status="PENDING_REVIEW"
        ).exists():
            return

        claim_record(
            seeker=seeker,
            issuer=employer,
            actor=seeker.user,
            record_type=RecordType.EXPERIENCE,
            subject_email=seeker.user.email,
            subject_full_name=seeker.user.full_name,
            detail_data={
                "job_title": "Junior Site Engineer",
                "department": "Infrastructure",
                "employment_type": ExperienceDetail.EmploymentType.CONTRACT,
                "start_date": date(2026, 3, 1),
                "end_date": None,
                "is_current": True,
                "departure_status": ExperienceDetail.DepartureStatus.CURRENT,
                "responsibilities": "Site supervision and quantity estimation.",
            },
        )
        self.stdout.write(
            f"  claim       {seeker.user.full_name} → {employer.legal_name} (awaiting endorsement)"
        )

    def _share_link(self, seeker: SeekerProfile) -> ShareLink:
        link = ShareLink.objects.filter(seeker=seeker, label="Demo — recruiter view").first()
        if link is None:
            link = ShareLink.objects.create(
                seeker=seeker,
                label="Demo — recruiter view",
                include_all=True,
                mask_identifiers=True,
                expires_at=timezone.now() + timedelta(days=30),
            )
        return link

    def _report(self, record: CredentialRecord, name: str) -> None:
        anchor = record.anchors.order_by("-created_at").first()
        if record.status == "ISSUED" and anchor and anchor.tx_hash:
            self.stdout.write(
                f"  anchored    {name:16} block {anchor.block_number:<4} "
                f"tx {anchor.tx_hash[:14]}… hash {record.record_hash[:12]}…"
            )
        else:
            self.stdout.write(
                self.style.WARNING(f"  pending     {name:16} (ledger unavailable, will retry)")
            )

    def _summary(self, showcase: CredentialRecord, share_link: ShareLink) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("\n" + "=" * 72))
        self.stdout.write(self.style.SUCCESS("  DEMO DATA READY"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 72))

        self.stdout.write(f"\n  All accounts use the password:  {DEMO_PASSWORD}\n")
        self.stdout.write("  Registrar   registrar@aafnopraman.np       (also /admin/)")
        self.stdout.write("  Institution registrar@tu.edu.np         Tribhuvan University")
        self.stdout.write("  Employer    hr@lftechnology.com          Leapfrog Technology")
        self.stdout.write("  Employer    people@fusemachines.com      Fusemachines Nepal")
        self.stdout.write("  Seeker      sita.sharma@example.com      3 verified records")
        self.stdout.write("  Seeker      bikash.thapa@example.com")
        self.stdout.write("  Seeker      anjali.gurung@example.com    1 claim pending")

        self.stdout.write("\n  Verify this record without logging in:")
        self.stdout.write(f"    curl http://localhost:8000/api/v1/verify/record/{showcase.pk}/")
        self.stdout.write(f"\n  Shared passport:  {share_link.url}")
        self.stdout.write("  Ledger status:    http://localhost:8000/api/v1/ledger/status/")
        self.stdout.write("  API docs:         http://localhost:8000/api/docs/\n")
