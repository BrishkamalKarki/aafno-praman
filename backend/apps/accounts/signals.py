"""
Account signals.

Two jobs, both of which must happen for every citizen account however it was
created — the API, a management command, a fixture or the admin — which is
exactly what signals are for.

## On linking records by email

An earlier revision removed this, on the grounds that attaching credentials by
email address is an identity check by mailbox possession. Under an
email-primary account model that objection no longer applies the same way, but
the underlying risk is real and is handled by *when* the link happens rather
than whether it does:

    linking a record to an account  ≠  the holder accepting it

A record linked here arrives as **awaiting confirmation** and is not anchored,
not published, and not visible to any verifier. It becomes real only when the
person who controls that mailbox confirms it. So an attacker who registers a
graduate's address first inherits a pending offer they must still act on, in
full view of the real holder's inbox — not a silently acquired degree.
"""

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Role, SeekerProfile, User
from .services import _unique_slug


@receiver(post_save, sender=User, dispatch_uid="accounts.create_citizen_profile")
def create_citizen_profile(sender, instance: User, created: bool, **kwargs) -> None:
    """Give every citizen account a credential passport."""
    if not created or instance.role != Role.SEEKER:
        return
    SeekerProfile.objects.get_or_create(
        user=instance,
        defaults={"public_slug": _unique_slug(), "legal_name": instance.full_name},
    )


@receiver(post_save, sender=User, dispatch_uid="accounts.attach_pending_records")
def attach_pending_records(sender, instance: User, created: bool, **kwargs) -> None:
    """
    Attach credentials already issued to this address.

    An institution issues at graduation, before the graduate has heard of the
    platform; the record waits against their email with a null subject. When
    they register, their passport is already populated — with everything still
    awaiting their confirmation.
    """
    if not created or instance.role != Role.SEEKER:
        return

    from apps.credentials.models import CredentialRecord

    def _link() -> None:
        profile = SeekerProfile.objects.filter(user=instance).first()
        if profile is None:
            return
        CredentialRecord.objects.filter(
            subject__isnull=True, subject_email__iexact=instance.email
        ).update(subject=profile)

    # After commit, so the profile created by the sibling receiver is visible.
    transaction.on_commit(_link)


@receiver(post_save, sender=User, dispatch_uid="accounts.audit_user_created")
def audit_user_created(sender, instance: User, created: bool, **kwargs) -> None:
    """
    Record account creation in the append-only audit trail.

    Imported lazily because ``apps.audit`` imports ``accounts.User`` for its
    actor foreign key; a module-level import would close the cycle at load.
    """
    if not created:
        return

    from apps.audit.models import AuditAction
    from apps.audit.services import record_event

    record_event(
        AuditAction.USER_REGISTERED,
        actor=instance,
        obj=instance,
        metadata={"role": instance.role},
    )
