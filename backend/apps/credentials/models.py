"""
Credential records — the domain core.

One ``CredentialRecord`` table carries the shared lifecycle (status, hash,
issuer, subject, anchoring), with a typed detail table per record type holding
the fields that differ. See ``docs/DATABASE.md`` §2.2 for why this beats both a
nullable mega-table and an unvalidated JSON blob.

The status machine reconciles the proposal's two contradictory issuance
descriptions (HR-06). §4.1 Flow B says the employer pushes records directly with
no employee submission; §6.2 says the seeker logs history which is "routed to
past employers for endorsement". Both are real product flows, so both exist here
as entry points into one machine:

    AUTHORITY_PUSH:  DRAFT ─────────────────► PENDING_ANCHOR ──► ISSUED
    SEEKER_CLAIM:    DRAFT ─► PENDING_REVIEW ─► PENDING_ANCHOR ──► ISSUED
                                  └──────────► REJECTED
    from ISSUED:                               REVOKED | SUPERSEDED
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.utils import normalise_text
from apps.common.validators import UploadValidator, validate_record_hash


class RecordType(models.TextChoices):
    ACADEMIC = "ACADEMIC", _("Academic credential")
    EXPERIENCE = "EXPERIENCE", _("Work experience")
    CERTIFICATION = "CERTIFICATION", _("Professional certification")


class RecordStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    # --- the consent gate ---------------------------------------------------
    OFFERED = "OFFERED", _("Awaiting the holder's confirmation")
    DECLINED = "DECLINED", _("Declined by the holder")
    EXPIRED = "EXPIRED", _("Confirmation link expired")
    # --- seeker-initiated claims --------------------------------------------
    PENDING_REVIEW = "PENDING_REVIEW", _("Awaiting issuer endorsement")
    REJECTED = "REJECTED", _("Rejected by issuer")
    # --- issuance -----------------------------------------------------------
    PENDING_ANCHOR = "PENDING_ANCHOR", _("Awaiting ledger anchor")
    ISSUED = "ISSUED", _("Issued and anchored")
    REVOKED = "REVOKED", _("Revoked")
    SUPERSEDED = "SUPERSEDED", _("Superseded by a correction")


class IssuanceMode(models.TextChoices):
    AUTHORITY_PUSH = "AUTHORITY_PUSH", _("Pushed by the issuing authority")
    SEEKER_CLAIM = "SEEKER_CLAIM", _("Claimed by the seeker, endorsed by the issuer")


#: Statuses in which a record occupies its natural key, and in which a hash must
#: already exist.
#:
#: ``OFFERED`` is included on purpose. The holder is shown the exact hash that
#: will be anchored before they confirm, so it has to be computed at offer time —
#: and an outstanding offer must block a duplicate one, or an issuer clicking
#: twice sends the same graduate two confirmation emails for one degree.
#:
#: ``DECLINED`` and ``EXPIRED`` are excluded, which is what lets an issuer
#: correct a mistake and re-offer.
LIVE_STATUSES = [
    RecordStatus.OFFERED,
    RecordStatus.PENDING_ANCHOR,
    RecordStatus.ISSUED,
    RecordStatus.REVOKED,
    RecordStatus.SUPERSEDED,
]

#: Statuses whose data is frozen — the hash is committed, so edits are tampering.
#:
#: ``OFFERED`` again: the holder consented to specific contents. An issuer
#: editing the degree title after the graduate confirmed would anchor something
#: nobody agreed to, so the API must refuse rather than merely detect it.
IMMUTABLE_STATUSES = [
    RecordStatus.OFFERED,
    RecordStatus.PENDING_ANCHOR,
    RecordStatus.ISSUED,
    RecordStatus.REVOKED,
    RecordStatus.SUPERSEDED,
]


class BatchStatus(models.TextChoices):
    PARSING = "PARSING", _("Parsing")
    PARTIAL = "PARTIAL", _("Completed with errors")
    COMPLETED = "COMPLETED", _("Completed")
    FAILED = "FAILED", _("Failed")


class IssuanceBatch(BaseModel):
    """
    A bulk upload — one graduating batch, one CSV, one chain transaction.

    Proposal §5.2 promises institutions "minimal manual input" and §8 Phase I
    scopes the pilot to a single graduating batch. A registrar's office works in
    spreadsheets, so CSV import is not a nice-to-have; it is the difference
    between adoption and a form nobody fills in 180 times.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="batches"
    )
    uploaded_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    record_type = models.CharField(max_length=20, choices=RecordType.choices)
    source_filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20, choices=BatchStatus.choices, default=BatchStatus.PARSING
    )
    total_rows = models.PositiveIntegerField(default=0)
    accepted_rows = models.PositiveIntegerField(default=0)
    rejected_rows = models.PositiveIntegerField(default=0)
    anchor_tx_hash = models.CharField(max_length=66, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "credentials_issuancebatch"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.source_filename} ({self.accepted_rows}/{self.total_rows})"


class BatchRowError(BaseModel):
    """
    A rejected CSV row, kept with its original content and the reason.

    Discarding bad rows silently would be the cruelest possible bug here: a
    graduate whose row failed validation would simply have no degree on the
    platform, with nobody aware. Every rejection is recorded and reported back.
    """

    batch = models.ForeignKey(IssuanceBatch, on_delete=models.CASCADE, related_name="errors")
    row_number = models.PositiveIntegerField()
    raw_row = models.JSONField(default=dict)
    error = models.TextField()

    class Meta:
        db_table = "credentials_batchrowerror"
        ordering = ["row_number"]

    def __str__(self) -> str:
        return f"Row {self.row_number}: {self.error[:60]}"


class CredentialRecord(BaseModel):
    """A single issued (or in-flight) credential."""

    record_type = models.CharField(max_length=20, choices=RecordType.choices)
    status = models.CharField(
        max_length=20,
        choices=RecordStatus.choices,
        default=RecordStatus.DRAFT,
        db_index=True,
    )
    issuance_mode = models.CharField(
        max_length=20, choices=IssuanceMode.choices, default=IssuanceMode.AUTHORITY_PUSH
    )

    issuer = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="issued_records"
    )
    subject = models.ForeignKey(
        "accounts.SeekerProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="records",
        help_text=_("Null until the subject registers an account."),
    )
    subject_email = models.EmailField(
        help_text=_(
            "How a pushed record finds its owner. An institution issues at "
            "graduation, before the graduate has an account; the record links "
            "itself when they sign up with this address."
        )
    )
    subject_full_name = models.CharField(
        max_length=150,
        help_text=_("Name as it appears on the credential. Part of the hashed payload."),
    )

    # ---- integrity ---------------------------------------------------------
    record_hash = models.CharField(
        max_length=64,
        blank=True,
        validators=[validate_record_hash],
        help_text=_("keccak256 of the canonical payload, lowercase hex, no 0x prefix."),
    )
    canonical_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            "Frozen snapshot of exactly what was hashed at issuance. Kept for "
            "audit and for showing verifiers the pre-image — never trusted as "
            "the source of truth during verification, which always recomputes "
            "from the live detail rows."
        ),
    )
    dedupe_key = models.CharField(max_length=64, blank=True)

    # ---- subject binding ---------------------------------------------------
    #
    # Binds this credential to a citizen *cryptographically, without disclosing
    # which one*. A verifier holding both the document and a claimed citizenship
    # number can recompute this and confirm the match; someone holding only
    # public chain data cannot work backwards to a person, because the salt
    # never leaves the database.
    #
    # Both values are FROZEN AT ISSUANCE rather than recomputed from the
    # holder's profile. If the payload derived them live, a holder whose
    # citizenship was attested *after* a credential was issued would suddenly
    # rehash differently and every one of their existing records would verify as
    # TAMPERED — accusing an honest graduate of forgery for updating a profile.
    subject_binding = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("Salted HMAC of the holder's citizenship number. Blank when they have none."),
    )
    binding_salt = models.CharField(
        max_length=32,
        blank=True,
        help_text=_(
            "Per-record salt. Off-chain only — this is what stops cross-record correlation."
        ),
    )

    document = models.FileField(
        upload_to="credentials/%Y/%m/", blank=True, null=True, validators=[UploadValidator()]
    )
    document_sha256 = models.CharField(max_length=64, blank=True)

    batch = models.ForeignKey(
        IssuanceBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="records"
    )
    superseded_by = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supersedes",
    )

    # ---- consent trail (AUTHORITY_PUSH path) -------------------------------
    offered_at = models.DateTimeField(null=True, blank=True)
    offer_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("After this the confirmation link stops working and the offer lapses."),
    )
    subject_responded_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.TextField(
        blank=True,
        help_text=_("Optional note from the holder. Feeds the issuer's correction flow."),
    )

    # ---- review trail (SEEKER_CLAIM path) ----------------------------------
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "credentials_credentialrecord"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["record_hash"],
                condition=~models.Q(record_hash=""),
                name="record_hash_unique_when_set",
            ),
            # E-11 / HR-09: the same graduate cannot hold two live credentials for
            # the same degree from the same institution, so re-uploading a batch
            # CSV is idempotent at the database level and not merely in code.
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=models.Q(status__in=LIVE_STATUSES) & ~models.Q(dedupe_key=""),
                name="record_dedupe_unique_while_live",
            ),
            models.CheckConstraint(
                check=~models.Q(status="ISSUED") | models.Q(issued_at__isnull=False),
                name="record_issued_requires_issued_at",
            ),
            models.CheckConstraint(
                check=~models.Q(status__in=LIVE_STATUSES) | ~models.Q(record_hash=""),
                name="record_live_requires_hash",
            ),
        ]
        indexes = [
            models.Index(fields=["issuer", "status"]),
            models.Index(fields=["subject", "record_type"]),
            models.Index(fields=["subject_email"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_record_type_display()} for {self.subject_full_name}"

    def save(self, *args, **kwargs):
        self.subject_email = self.subject_email.lower().strip()
        self.subject_full_name = normalise_text(self.subject_full_name)
        super().save(*args, **kwargs)

    # ---- derived state -----------------------------------------------------

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES

    @property
    def is_editable(self) -> bool:
        """
        Whether the detail fields may still change.

        Once a hash is committed, editing the data is by definition tampering —
        the API enforces this so an over-eager PATCH cannot silently invalidate
        an already-issued QR code.
        """
        return self.status not in IMMUTABLE_STATUSES

    @property
    def detail(self):
        """The typed detail row, whichever kind this record is."""
        if self.record_type == RecordType.EXPERIENCE:
            return getattr(self, "experience_detail", None)
        return getattr(self, "academic_detail", None)

    @property
    def awaiting_holder(self) -> bool:
        return self.status == RecordStatus.OFFERED

    @property
    def is_offer_expired(self) -> bool:
        return (
            self.status == RecordStatus.OFFERED
            and self.offer_expires_at is not None
            and timezone.now() >= self.offer_expires_at
        )

    def mark_issued(self) -> None:
        self.status = RecordStatus.ISSUED
        self.issued_at = self.issued_at or timezone.now()
        self.save(update_fields=["status", "issued_at", "updated_at"])


class AcademicDetail(BaseModel):
    """Academic-specific fields — proposal §6.1 'Verified Data'."""

    class Level(models.TextChoices):
        SCHOOL = "SCHOOL", _("School Leaving Certificate")
        PLUS_TWO = "PLUS_TWO", _("Higher Secondary (+2)")
        DIPLOMA = "DIPLOMA", _("Diploma")
        BACHELORS = "BACHELORS", _("Bachelor's")
        MASTERS = "MASTERS", _("Master's")
        DOCTORATE = "DOCTORATE", _("Doctorate")
        CERTIFICATE = "CERTIFICATE", _("Certificate course")

    record = models.OneToOneField(
        CredentialRecord, on_delete=models.CASCADE, related_name="academic_detail"
    )
    registration_number = models.CharField(
        max_length=64, help_text=_("Roll or registration number issued by the institution.")
    )
    degree_title = models.CharField(max_length=200)
    major = models.CharField(max_length=150, blank=True)
    level = models.CharField(max_length=20, choices=Level.choices)
    graduation_date = models.DateField(help_text=_("Gregorian. This is the canonical date."))
    graduation_date_bs = models.CharField(
        max_length=12,
        blank=True,
        help_text=_(
            "Bikram Sambat date as printed on the certificate, e.g. 2081-04-15. "
            "Display only: the Gregorian date is what gets hashed, because BS "
            "conversion tables differ between sources and a hash must not depend "
            "on which table the issuer used."
        ),
    )
    cgpa = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("4"))],
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    honours = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "credentials_academicdetail"
        constraints = [
            models.CheckConstraint(
                check=models.Q(cgpa__isnull=True) | models.Q(cgpa__gte=0, cgpa__lte=4),
                name="academic_cgpa_range",
            ),
            models.CheckConstraint(
                check=models.Q(percentage__isnull=True)
                | models.Q(percentage__gte=0, percentage__lte=100),
                name="academic_percentage_range",
            ),
        ]
        indexes = [models.Index(fields=["registration_number"])]

    def __str__(self) -> str:
        return f"{self.degree_title} ({self.graduation_date.year})"


class ExperienceDetail(BaseModel):
    """Employment-specific fields — proposal §6.2."""

    class EmploymentType(models.TextChoices):
        FULL_TIME = "FULL_TIME", _("Full time")
        PART_TIME = "PART_TIME", _("Part time")
        CONTRACT = "CONTRACT", _("Contract")
        INTERNSHIP = "INTERNSHIP", _("Internship")
        CONSULTANT = "CONSULTANT", _("Consultant")

    class DepartureStatus(models.TextChoices):
        CURRENT = "CURRENT", _("Currently employed")
        RESIGNED = "RESIGNED", _("Resigned")
        CONTRACT_ENDED = "CONTRACT_ENDED", _("Contract ended")
        RETIRED = "RETIRED", _("Retired")
        TERMINATED = "TERMINATED", _("Terminated")

    record = models.OneToOneField(
        CredentialRecord, on_delete=models.CASCADE, related_name="experience_detail"
    )
    job_title = models.CharField(max_length=150)
    department = models.CharField(max_length=150, blank=True)
    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    start_date = models.DateField()
    end_date = models.DateField(
        null=True, blank=True, help_text=_("Null while the employee is still with the company.")
    )
    is_current = models.BooleanField(default=False)
    departure_status = models.CharField(max_length=20, choices=DepartureStatus.choices)
    responsibilities = models.TextField(
        blank=True, help_text=_("Ordered list is preserved in the hash; wording matters.")
    )

    class Meta:
        db_table = "credentials_experiencedetail"
        constraints = [
            # E-06: 'current' and 'has an end date' must never disagree. Title
            # inflation is the headline fraud (§6.2), but a tenure that claims to
            # be both ongoing and ended is how date fraud hides.
            models.CheckConstraint(
                check=(
                    models.Q(is_current=True, end_date__isnull=True)
                    | models.Q(is_current=False, end_date__isnull=False)
                ),
                name="experience_current_xor_end_date",
            ),
            models.CheckConstraint(
                check=models.Q(end_date__isnull=True)
                | models.Q(end_date__gte=models.F("start_date")),
                name="experience_end_after_start",
            ),
        ]
        indexes = [models.Index(fields=["job_title"])]

    def __str__(self) -> str:
        end = "present" if self.is_current else self.end_date
        return f"{self.job_title} ({self.start_date} – {end})"


class CredentialConfirmation(BaseModel):
    """
    The "is this you?" link sent to a credential's subject.

    ## Why this gates the ledger

    An anchor is permanent and public. Writing one before the person it describes
    has agreed would publish a claim about them that can never be withdrawn —
    so the confirmation is not a notification, it is the gate. Nothing reaches
    the chain until this row is confirmed.

    ## Why only the hash is stored

    The plaintext token exists once, in the email. A support engineer reading
    this table, or an attacker reading a database dump, gets nothing they can
    redeem. Plain SHA-256 is correct here — unlike for a citizenship number the
    token is 256 bits of uniform randomness, so there is no keyspace to
    enumerate and a pepper would add nothing.

    ## Why sends are capped as well as attempts

    ``attempts`` bounds guessing. ``send_count`` bounds something different and
    easier to overlook: without it, "resend my confirmation" is a free
    mail-bomb aimed at any address an attacker names, using the platform's own
    reputation to deliver it.
    """

    record = models.OneToOneField(
        CredentialRecord, on_delete=models.CASCADE, related_name="confirmation"
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    sent_to = models.EmailField(
        help_text=_("The address the issuer supplied. Recorded for dispute resolution.")
    )
    expires_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(
        default=0, help_text=_("Failed redemption attempts. Bounded to stop token guessing.")
    )
    send_count = models.PositiveSmallIntegerField(default=1)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    MAX_ATTEMPTS = 5
    MAX_SENDS = 5

    class Meta:
        db_table = "credentials_confirmation"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["expires_at"])]

    def __str__(self) -> str:
        return f"Confirmation for {self.record_id} -> {self.sent_to}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_answered(self) -> bool:
        return self.confirmed_at is not None or self.declined_at is not None

    @property
    def is_exhausted(self) -> bool:
        return self.attempts >= self.MAX_ATTEMPTS

    @property
    def is_open(self) -> bool:
        return not (self.is_answered or self.is_expired or self.is_exhausted)

    @property
    def can_resend(self) -> bool:
        return self.is_open and self.send_count < self.MAX_SENDS
