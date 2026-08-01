"""
Citizen account services — provisioning and citizenship attestation.

## The identity model, in one paragraph

An account is an email address. It is created either by the person signing up,
or implicitly when an approved issuer issues a credential to an address that has
no account yet — in which case nothing is published until a confirmation token
sent to that address is redeemed. A citizenship number is optional; when an
issuer supplies one it is attested, not asserted, because the issuer already
holds it on file to print the certificate at all.

## What this buys and what it does not

With a citizenship number on file, a verifier can be told whether a genuine
certificate really belongs to the person they named. Without one, the platform
can only say the certificate is genuine and unaltered. ``IdentityLevel`` records
which applies so the verification response can state the limit rather than imply
a guarantee that was never established.

The residual risk — whoever controls the mailbox controls the account — is
inherent to email-first credential platforms and is documented on
``SeekerProfile`` rather than glossed over.
"""

from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import ConflictError

from . import identity as identity_crypto
from .models import IdentityLevel, Role, SeekerProfile, User

logger = logging.getLogger(__name__)


class CitizenshipConflict(ConflictError):
    default_code = "citizenship_already_claimed"
    default_detail = "This citizenship number is already attached to another account."


def _unique_slug() -> str:
    """
    Random passport slug.

    Deliberately not derived from the holder's name: a guessable slug such as
    ``/p/ram-sharma`` would make a person's credential passport discoverable by
    anyone who knows their name, which is precisely the enumeration exposure the
    share-link privacy controls exist to prevent.
    """
    for _attempt in range(10):
        slug = secrets.token_urlsafe(9).replace("_", "").replace("-", "").lower()[:12]
        if len(slug) >= 10 and not SeekerProfile.objects.filter(public_slug=slug).exists():
            return slug
    raise RuntimeError("Could not generate a unique passport slug.")


@transaction.atomic
def get_or_create_account(
    *, email: str, full_name: str = "", phone: str = ""
) -> tuple[SeekerProfile, bool]:
    """
    Find or create the citizen account for an email address.

    Returns ``(profile, created)``. Used both by self-registration and by
    issuance to an address that has no account yet.

    The account created here has **no usable password**. It is a placeholder the
    real person activates by redeeming a confirmation token sent to that
    address; until then it can hold pending credentials but cannot sign in.
    Creating it with a password would mean inventing a credential nobody asked
    for and nobody can rotate.
    """
    normalised = email.lower().strip()
    if not normalised:
        raise ValueError("An email address is required.")

    existing = SeekerProfile.objects.select_related("user").filter(user__email=normalised).first()
    if existing is not None:
        # A later issuer must not overwrite a name the holder already has on
        # their own account — that would let any approved issuer rewrite any
        # citizen's display identity.
        if full_name and not existing.legal_name:
            existing.legal_name = full_name
            existing.save(update_fields=["legal_name", "updated_at"])
        return existing, False

    user = User.objects.filter(email=normalised).first()
    if user is not None and user.role != Role.SEEKER:
        # An organisation staff account and a credential holder are different
        # things. Silently attaching a passport to an issuer's login would let
        # a university employee receive credentials as their institution.
        raise ConflictError(detail="This address is already registered as an organisation account.")

    if user is None:
        user = User(
            email=normalised,
            # A placeholder until an issuer supplies the real one. The column is
            # not nullable and this account exists before anyone has told us who
            # they are.
            full_name=full_name or normalised,
            phone=phone,
            role=Role.SEEKER,
        )
        user.set_unusable_password()
        user.save()

    # The profile is created by the `create_citizen_profile` post_save receiver,
    # not here. Creating it again would violate the OneToOne, and moving the
    # creation out of the signal would mean fixtures, management commands and
    # the admin each had to remember to do it.
    profile = SeekerProfile.objects.select_for_update().get(user=user)

    updates = []
    if full_name and not profile.legal_name:
        profile.legal_name = full_name
        updates.append("legal_name")
    if profile.identity_level != IdentityLevel.CITIZENSHIP:
        profile.identity_level = IdentityLevel.EMAIL_ONLY
        updates.append("identity_level")
    if updates:
        profile.save(update_fields=[*updates, "updated_at"])

    logger.info("Provisioned citizen account for %s", normalised)
    return profile, True


@transaction.atomic
def attest_citizenship(*, profile: SeekerProfile, national_id: str, organization) -> SeekerProfile:
    """
    Record an issuer's attestation of a holder's citizenship number.

    Idempotent for the same number, so re-uploading a batch CSV does not fail.
    Raises when the number already belongs to a different account — two people
    cannot share one citizenship number, and silently reassigning it would let
    the second issuer hijack the first holder's subject-match guarantee.

    Only ever called with a number an **approved** issuer supplied. There is no
    endpoint through which a holder can assert their own: self-assertion is what
    would make the CITIZENSHIP level meaningless.
    """
    id_hmac = identity_crypto.national_id_hmac(national_id)

    clash = SeekerProfile.objects.filter(national_id_hmac=id_hmac).exclude(pk=profile.pk).exists()
    if clash:
        raise CitizenshipConflict()

    if profile.national_id_hmac == id_hmac:
        return profile

    if profile.national_id_hmac:
        # Changing an already-attested number is a dispute, not a routine edit.
        # It goes through the registrar so there is a human and an audit trail
        # between "the university says otherwise" and a rewritten identity.
        raise ConflictError(
            detail=(
                "This account already has a different citizenship number on "
                "file. Correcting it requires registrar review."
            )
        )

    profile.national_id_hmac = id_hmac
    profile.national_id_ct = identity_crypto.encrypt_national_id(national_id)
    profile.hmac_version = settings.NATIONAL_ID_HMAC_VERSION
    profile.identity_level = IdentityLevel.CITIZENSHIP
    profile.citizenship_verified_by = organization
    profile.citizenship_verified_at = timezone.now()
    profile.save(
        update_fields=[
            "national_id_hmac",
            "national_id_ct",
            "hmac_version",
            "identity_level",
            "citizenship_verified_by",
            "citizenship_verified_at",
            "updated_at",
        ]
    )
    logger.info(
        "Citizenship attested for profile %s by %s",
        profile.pk,
        getattr(organization, "slug", "unknown"),
    )
    return profile


def profile_for_national_id(national_id: str) -> SeekerProfile | None:
    """
    Resolve a citizenship number to an account.

    Internal use only — issuance and dispute resolution. Deliberately **not**
    exposed through any endpoint: a public lookup keyed on citizenship number
    would be an enumeration oracle over a keyspace small enough to walk.
    """
    try:
        id_hmac = identity_crypto.national_id_hmac(national_id)
    except identity_crypto.IdentityError:
        return None
    return SeekerProfile.objects.select_related("user").filter(national_id_hmac=id_hmac).first()
