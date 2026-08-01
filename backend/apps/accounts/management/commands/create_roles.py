"""
Create the three standing role accounts: admin, issuer, viewer.

The platform has two independent role axes, and a frontend needs a login for
each level to exercise them:

* ``User.role``                  — SEEKER / ORG_MEMBER / REGISTRAR
* ``OrganizationMembership.role`` — OWNER / ISSUER / VIEWER

``admin`` is a platform REGISTRAR (and a Django superuser, so /admin/ works).
``issuer`` and ``viewer`` are ORG_MEMBERs of the same organisation, separated
only by their membership role — which is the whole point: it makes the
read-only versus can-anchor boundary testable with two logins rather than by
editing a row between requests.

Idempotent. Re-running updates nothing but the password, and only when
``--password`` is given explicitly.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, User
from apps.organizations.models import (
    MembershipRole,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

# Matches the convention already used by `seed_demo`. Local development only —
# these accounts are for a laptop and a demo, never for a deployed environment.
DEFAULT_PASSWORD = "AafnoPraman2026!"

ACCOUNTS = [
    {
        "key": "admin",
        "email": "admin@aafnopraman.np",
        "full_name": "Aafno Praman Administrator",
        "role": Role.REGISTRAR,
        "is_staff": True,
        "is_superuser": True,
        "membership": None,
    },
    {
        "key": "issuer",
        "email": "issuer@aafnopraman.np",
        "full_name": "Aafno Praman Issuer",
        "role": Role.ORG_MEMBER,
        "is_staff": False,
        "is_superuser": False,
        "membership": MembershipRole.ISSUER,
    },
    {
        "key": "viewer",
        "email": "viewer@aafnopraman.np",
        "full_name": "Aafno Praman Viewer",
        "role": Role.ORG_MEMBER,
        "is_staff": False,
        "is_superuser": False,
        "membership": MembershipRole.VIEWER,
    },
]


class Command(BaseCommand):
    help = "Create the admin, issuer and viewer role accounts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--org",
            dest="org_slug",
            default="",
            help=(
                "Slug of the organisation to attach the issuer and viewer to. "
                "Defaults to the first APPROVED organisation."
            ),
        )
        parser.add_argument(
            "--password",
            default="",
            help=f"Password for all three accounts (default: {DEFAULT_PASSWORD}).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"] or DEFAULT_PASSWORD
        reset_password = bool(options["password"])
        organization = self._organization(options["org_slug"])

        self.stdout.write(self.style.MIGRATE_HEADING("Creating role accounts…"))

        for spec in ACCOUNTS:
            user = self._user(spec, password, reset_password)
            if spec["membership"] is not None:
                self._membership(user, organization, spec["membership"])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Role accounts ready."))
        self.stdout.write(f"  organisation : {organization.legal_name} ({organization.slug})")
        self.stdout.write(f"  password     : {password}")

    # ------------------------------------------------------------------ steps

    def _organization(self, slug: str) -> Organization:
        """
        Resolve the organisation the issuer and viewer belong to.

        Requires an APPROVED organisation rather than creating one, because
        approval is chain-first: it generates a signing key and registers the
        issuer on the contract. Duplicating that here would either bypass the
        ledger — leaving an issuer the chain has never heard of — or fork a
        second copy of logic that already exists in `approve_organization`.
        """
        if slug:
            organization = Organization.objects.filter(slug=slug).first()
            if organization is None:
                raise CommandError(f"No organisation with slug '{slug}'.")
        else:
            organization = (
                Organization.objects.filter(status=OrganizationStatus.APPROVED)
                .order_by("created_at")
                .first()
            )
            if organization is None:
                raise CommandError(
                    "No approved organisation exists to attach the issuer and viewer to.\n"
                    "Run `python manage.py seed_demo` first (it needs the Hardhat node "
                    "running), or pass --org <slug>."
                )

        if organization.status != OrganizationStatus.APPROVED:
            self.stdout.write(
                self.style.WARNING(
                    f"  note: '{organization.slug}' is {organization.status}, not APPROVED. "
                    "The issuer account cannot anchor credentials until it is approved."
                )
            )
        return organization

    def _user(self, spec: dict, password: str, reset_password: bool) -> User:
        user = User.objects.filter(email=spec["email"]).first()

        if user is None:
            user = User.objects.create_user(
                email=spec["email"],
                password=password,
                full_name=spec["full_name"],
                role=spec["role"],
                is_staff=spec["is_staff"],
                is_superuser=spec["is_superuser"],
            )
            action = "created"
        else:
            # Bring an existing account in line with the spec — a viewer that
            # somehow holds is_superuser is worth correcting on every run.
            user.role = spec["role"]
            user.is_staff = spec["is_staff"]
            user.is_superuser = spec["is_superuser"]
            if reset_password:
                user.set_password(password)
            user.save()
            action = "updated"

        self.stdout.write(f"  {action:<8} {spec['key']:<7} {user.email:<22} User.role={user.role}")
        return user

    def _membership(self, user: User, organization: Organization, role: str) -> None:
        membership, created = OrganizationMembership.objects.get_or_create(
            user=user, organization=organization, defaults={"role": role}
        )
        if not created and membership.role != role:
            membership.role = role
            membership.save(update_fields=["role"])

        self.stdout.write(
            f"           {'':<7} {'':<22} Membership.role={role} @ {organization.slug}"
        )
