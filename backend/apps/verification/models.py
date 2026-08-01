"""
Sharing and verification.

Implements proposal §6.3's "Credential Passport" sharing controls and the §9
metering that makes the employer freemium tier real rather than aspirational.
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.utils import generate_token


class VerificationResult(models.TextChoices):
    """
    The seven possible outcomes of a verification.

    Collapsing these into a boolean would be the dishonest simplification. A
    recruiter needs to distinguish "the data was altered" from "the university
    withdrew this degree" from "our node is briefly unreachable" — those demand
    three different human responses, and showing a red cross for all of them
    would make the platform untrustworthy in the opposite direction.

    ``SUBJECT_MISMATCH`` is the fraud case the others miss: a completely genuine,
    unaltered, un-revoked certificate that simply belongs to somebody else. It
    can only be reported for holders whose citizenship number an approved issuer
    attested — for an email-only account there is nothing to check the claim
    against, and the response says so rather than implying a guarantee that was
    never established.
    """

    VERIFIED = "VERIFIED", _("Verified")
    SUBJECT_MISMATCH = "SUBJECT_MISMATCH", _("Genuine, but not issued to that person")
    TAMPERED = "TAMPERED", _("Data does not match the ledger")
    REVOKED = "REVOKED", _("Revoked by the issuer")
    SUPERSEDED = "SUPERSEDED", _("Superseded by a corrected record")
    UNCONFIRMED = "UNCONFIRMED", _("Signature valid, ledger unreachable")
    NOT_FOUND = "NOT_FOUND", _("No such record")


class ShareLink(BaseModel):
    """
    A scoped, revocable, optionally passphrase-protected view of a passport.

    Proposal §6.3 asks for expiry, passphrase protection and hidden ID numbers.
    All three are per-link rather than per-account, because a seeker sharing with
    a trusted recruiter and sharing on a public job board have genuinely
    different privacy needs for the same underlying records.
    """

    seeker = models.ForeignKey(
        "accounts.SeekerProfile", on_delete=models.CASCADE, related_name="share_links"
    )
    token = models.CharField(max_length=64, unique=True, default=generate_token, editable=False)
    label = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("For the seeker's own reference, e.g. 'Deerwalk application'."),
    )

    include_all = models.BooleanField(
        default=True,
        help_text=_("Share everything, including records issued after this link was created."),
    )
    mask_identifiers = models.BooleanField(
        default=True,
        help_text=_("Mask registration and national ID numbers in the shared view (§6.3)."),
    )
    passphrase_hash = models.CharField(max_length=128, blank=True)

    expires_at = models.DateTimeField(null=True, blank=True, help_text=_("Null means no expiry."))
    max_views = models.PositiveIntegerField(
        null=True, blank=True, help_text=_("Null means unlimited.")
    )
    view_count = models.PositiveIntegerField(default=0)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "verification_sharelink"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["seeker", "-created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return self.label or f"Share link {self.token[:8]}…"

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and timezone.now() >= self.expires_at

    @property
    def is_exhausted(self) -> bool:
        return self.max_views is not None and self.view_count >= self.max_views

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_active(self) -> bool:
        return not (self.is_revoked or self.is_expired or self.is_exhausted)

    @property
    def requires_passphrase(self) -> bool:
        return bool(self.passphrase_hash)

    @property
    def url(self) -> str:
        from django.conf import settings

        return f"{settings.PUBLIC_APP_URL}/s/{self.token}"


class ShareLinkRecord(BaseModel):
    """
    Explicit record selection for a link where ``include_all`` is false.

    Selective sharing matters more than it first appears: a candidate applying
    for one job should be able to prove the relevant degree without disclosing
    that they were let go from a previous employer.
    """

    share_link = models.ForeignKey(ShareLink, on_delete=models.CASCADE, related_name="selections")
    record = models.ForeignKey(
        "credentials.CredentialRecord", on_delete=models.CASCADE, related_name="share_selections"
    )

    class Meta:
        db_table = "verification_sharelinkrecord"
        constraints = [
            models.UniqueConstraint(fields=["share_link", "record"], name="sharelink_record_unique")
        ]


class VerificationLog(BaseModel):
    """
    One verification attempt.

    Powers the §9 employer quota, the paid-tier analytics dashboard, and abuse
    detection. IPs are stored hashed (see ``docs/DATABASE.md`` §2.5): a public
    service that kept raw IPs beside credential hashes would be building a record
    of who investigated whose qualifications.
    """

    record = models.ForeignKey(
        "credentials.CredentialRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verifications",
    )
    record_hash = models.CharField(max_length=64, blank=True, db_index=True)
    lookup_reference = models.CharField(
        max_length=128, blank=True, help_text=_("What the verifier actually typed or scanned.")
    )
    result = models.CharField(max_length=20, choices=VerificationResult.choices)

    verifier_org = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verifications_performed",
        help_text=_("Null for an anonymous QR scan — no account is required to verify."),
    )
    verifier_user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    share_link = models.ForeignKey(
        ShareLink, null=True, blank=True, on_delete=models.SET_NULL, related_name="views"
    )

    client_ip_hash = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    counts_against_quota = models.BooleanField(
        default=False,
        help_text=_(
            "Only authenticated employer lookups are metered. Anonymous scans are "
            "rate-limited instead, so a candidate sharing their own link with a "
            "recruiter never burns the recruiter's quota unexpectedly."
        ),
    )

    class Meta:
        db_table = "verification_log"
        ordering = ["-created_at"]
        indexes = [
            # Drives the monthly quota check on the hot path — see
            # QuotaService.lookups_this_month.
            models.Index(fields=["verifier_org", "-created_at"]),
            models.Index(fields=["result", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.result} @ {self.created_at:%Y-%m-%d %H:%M}"
