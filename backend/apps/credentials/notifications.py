"""
Outbound email for the credential confirmation flow.

Kept behind a thin module so the transport can change — console in development,
SMTP in the pilot, a provider API later — without any caller learning about it.

## On failure handling

Sending is best-effort and never raises into the issuance path. An issuer whose
graduation batch fails because an SMTP host was briefly unreachable would
reasonably conclude the platform is broken; the correct behaviour is to record
the credential, leave the offer outstanding, and let the issuer resend. The
alternative — losing the record because the mail server hiccuped — is the worse
error by a wide margin.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def confirmation_url(token: str) -> str:
    return f"{settings.PUBLIC_APP_URL}/confirm/{token}"


def send_confirmation_email(*, record, token: str, to_email: str) -> bool:
    """
    Ask a credential's subject to confirm it is theirs.

    Returns whether the message was handed to the transport. The copy states
    plainly what confirming does, because "click here to verify" trains people
    to click links in unexpected email — which is the exact behaviour that makes
    credential phishing work.
    """
    issuer = record.issuer.legal_name
    title = _describe(record)
    url = confirmation_url(token)

    subject = f"{issuer} has issued you a credential — please confirm"
    body = (
        f"Hello,\n\n"
        f"{issuer} says they issued you the following credential on Aafno Praman:\n\n"
        f"    {title}\n\n"
        f"Nothing is published until you confirm. If you confirm, a "
        f"cryptographic fingerprint of this record is written to a public "
        f"ledger so employers can verify it. The certificate document itself is "
        f"never published.\n\n"
        f"Confirm or decline here:\n{url}\n\n"
        f"This link expires in {settings.CREDENTIAL_CONFIRM_TTL_HOURS} hours and "
        f"can only be used once.\n\n"
        f"If this is not you, or you were not expecting this, decline it at the "
        f"link above — that tells {issuer} they have the wrong address. Do not "
        f"forward this email: anyone holding the link can answer on your "
        f"behalf.\n\n"
        f"— Aafno Praman\n"
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@aafnopraman.np"),
            recipient_list=[to_email],
            fail_silently=False,
        )
        return True
    except Exception:
        # Logged, never raised. See the module docstring.
        logger.exception(
            "Failed to send confirmation email for record %s to %s", record.pk, to_email
        )
        return False


def _describe(record) -> str:
    """Human summary of a record, for email subject lines and link previews."""
    detail = record.detail
    if detail is None:
        return record.get_record_type_display()
    title = getattr(detail, "degree_title", None) or getattr(detail, "job_title", "")
    return title or record.get_record_type_display()
