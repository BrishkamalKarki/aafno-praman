"""
User accounts.

Three primary roles, chosen so that a single user record can never be quietly
both a credential subject and an issuer:

* ``SEEKER``     — owns a credential passport; the subject of records.
* ``ORG_MEMBER`` — acts on behalf of an institution or employer.
* ``REGISTRAR``  — platform staff; the root of trust that approves issuers.

Organisation-level permissions are *not* stored here. A user's authority to
issue comes from an ``OrganizationMembership`` row plus that organisation's
approved status, so revoking an institution's approval instantly removes every
one of its staff members' ability to issue without touching any user record.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import UUIDModel
from apps.common.utils import normalise_text


class Role(models.TextChoices):
    SEEKER = "SEEKER", _("Job seeker")
    ORG_MEMBER = "ORG_MEMBER", _("Organisation member")
    REGISTRAR = "REGISTRAR", _("Platform registrar")


class UserManager(BaseUserManager):
    """Manager for the email-as-username custom user."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        # Normalising to lowercase in one place is what makes the unique
        # constraint meaningful: 'Ram@x.com' and 'ram@x.com' must not be two
        # accounts. A Postgres CITEXT column would also work but would break the
        # SQLite path used by the test suite.
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("role", Role.SEEKER)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("role", Role.REGISTRAR)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("A superuser must have is_staff and is_superuser set.")
        return self._create_user(email, password, **extra)


class User(UUIDModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(_("email address"), unique=True, max_length=254)
    full_name = models.CharField(_("full name"), max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SEEKER)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False,
        help_text=_("Grants access to the registrar console at /admin/."),
    )
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "accounts_user"
        ordering = ["-date_joined"]
        indexes = [models.Index(fields=["role"])]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        self.full_name = normalise_text(self.full_name)
        super().save(*args, **kwargs)

    @property
    def is_registrar(self) -> bool:
        return self.role == Role.REGISTRAR

    @property
    def is_seeker(self) -> bool:
        return self.role == Role.SEEKER

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else self.email


class IdentityLevel(models.TextChoices):
    """
    How strongly this account is tied to a real person.

    The platform accepts both levels deliberately. Requiring a citizenship
    number to sign up would exclude anyone who does not have one to hand and
    stall adoption at the front door; requiring nothing at all would make the
    "is this really that person?" question unanswerable. So email is the floor,
    citizenship is the ceiling, and **verification results say which applies**
    rather than implying a guarantee the account cannot support.
    """

    EMAIL_ONLY = "EMAIL_ONLY", _("Email confirmed")
    CITIZENSHIP = "CITIZENSHIP", _("Citizenship number verified by an issuer")


class SeekerProfile(UUIDModel):
    """
    A citizen's credential passport.

    ## Identity model

    The account is keyed on **email**, which is ``User.email`` — unique, and the
    only login credential. Phone is contact detail. The citizenship number is
    optional, and this is the model's central trade-off, made explicitly:

    * **Without one** the platform can prove a certificate is genuine and
      unaltered, but cannot prove *who* it belongs to beyond "the person who
      controls this mailbox".
    * **With one**, attested by the approved issuer that already holds it on
      file, a verifier can additionally confirm the certificate really was
      issued to the citizen they named.

    ``identity_level`` records which of those a given account supports, and the
    verification response carries it, so the UI can state the limit honestly
    instead of implying a subject guarantee that was never established.

    ## Why the number is never stored in the clear

    A Nepali citizenship number is district-structured and sequentially issued,
    so the plausible keyspace is small enough to walk exhaustively — a plain
    hash of one is a reversible index of the population. Lookups use an HMAC
    under a pepper the database does not contain, and anything reaching the
    public ledger is additionally salted per record. See
    ``apps/accounts/identity.py``.

    ## The residual risk of email-primary identity, stated plainly

    Whoever controls the mailbox controls the account. That is inherent to every
    email-first credential platform and is accepted here, bounded by two things:
    the issuer supplies the address from its own student or HR records rather
    than the recipient choosing it, and nothing is published until a token sent
    to that address is redeemed. An attacker must compromise a specific mailbox
    that an institution already had on file — not merely guess an identity.
    """

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="seeker_profile",
    )
    public_slug = models.SlugField(
        max_length=64,
        unique=True,
        help_text=_("Used in the passport URL. Random, not derived from the name."),
    )
    legal_name = models.CharField(
        max_length=150,
        blank=True,
        help_text=_("Name as it appears on credentials. Set from the first issuance."),
    )
    headline = models.CharField(max_length=160, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # ---- optional national identity ---------------------------------------
    national_id_hmac = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_("HMAC-SHA256 of the citizenship number. Blank when not supplied."),
    )
    national_id_ct = models.BinaryField(
        blank=True,
        default=b"",
        help_text=_("Fernet ciphertext of the number. Read only for dispute resolution."),
    )
    hmac_version = models.PositiveSmallIntegerField(
        default=1,
        help_text=_("Which pepper generation produced national_id_hmac. Enables rotation."),
    )
    identity_level = models.CharField(
        max_length=20,
        choices=IdentityLevel.choices,
        default=IdentityLevel.EMAIL_ONLY,
        help_text=_("What a verifier may rely on. Drives the subject-match guarantee."),
    )
    citizenship_verified_by = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=_("The approved issuer that attested to the citizenship number."),
    )
    citizenship_verified_at = models.DateTimeField(null=True, blank=True)

    is_discoverable = models.BooleanField(
        default=False,
        help_text=_(
            "Opt in to appearing in employer candidate search. Off by default: "
            "an open, searchable national credential registry would let anyone "
            "enumerate every citizen's education history (HR-07)."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_seekerprofile"
        constraints = [
            # Partial unique: most accounts legitimately have no citizenship
            # number, and blank values must not collide with one another. When
            # one *is* set it still identifies exactly one person.
            models.UniqueConstraint(
                fields=["national_id_hmac"],
                condition=~models.Q(national_id_hmac=""),
                name="identity_national_id_unique_when_set",
            ),
            # CITIZENSHIP level without a number is a claim the account cannot
            # support, and it would make the verifier's subject-match guarantee
            # a lie. Enforced in the database because the API is not the only
            # writer — the admin, fixtures and management commands reach here too.
            models.CheckConstraint(
                condition=(
                    ~models.Q(identity_level=IdentityLevel.CITIZENSHIP)
                    | ~models.Q(national_id_hmac="")
                ),
                name="identity_citizenship_level_requires_number",
            ),
        ]
        indexes = [
            models.Index(fields=["is_discoverable"]),
            models.Index(fields=["identity_level"]),
        ]

    def __str__(self) -> str:
        return f"Passport of {self.legal_name or self.user.email}"

    def save(self, *args, **kwargs):
        self.legal_name = normalise_text(self.legal_name)
        super().save(*args, **kwargs)

    @property
    def has_citizenship(self) -> bool:
        return bool(self.national_id_hmac)

    @property
    def email(self) -> str:
        """Contact and login address. Single-sourced from the user record."""
        return self.user.email

    @property
    def passport_url(self) -> str:
        from django.conf import settings

        return f"{settings.PUBLIC_APP_URL}/p/{self.public_slug}"
