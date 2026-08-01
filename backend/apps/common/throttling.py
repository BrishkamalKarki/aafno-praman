"""
Throttle classes.

Rates live in settings (`DEFAULT_THROTTLE_RATES`) so they are tunable per
environment without a code change.
"""

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle

from .utils import client_ip


class VerificationThrottle(AnonRateThrottle):
    """
    Rate-limits the public verification endpoint.

    Verification must stay open — requiring recruiters to register would defeat
    the "instant lookup" promise. The trade-off is that an open endpoint over a
    national credential registry is an obvious scraping target, so anonymous
    callers get a firm hourly ceiling while authenticated employers fall back to
    their plan quota instead.
    """

    scope = "verify_anon"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None  # authenticated employers are metered by quota, not rate
        return self.cache_format % {"scope": self.scope, "ident": client_ip(request)}


class AuthThrottle(AnonRateThrottle):
    """Slows credential stuffing against login and registration."""

    scope = "auth"


class ShareUnlockThrottle(SimpleRateThrottle):
    """
    Limits passphrase attempts on a protected share link (E-04).

    Keyed on the link token rather than the IP: an attacker rotating through
    proxies against one link is the threat, and legitimate viewers of a
    *different* link should not be punished for it.
    """

    scope = "share_unlock"

    def get_cache_key(self, request, view):
        token = view.kwargs.get("token", "")
        return self.cache_format % {"scope": self.scope, "ident": token}


class IssuanceThrottle(SimpleRateThrottle):
    """
    Caps issuance volume per organisation.

    A compromised issuer account minting thousands of fake degrees is the worst
    realistic attack on this platform. This bounds the damage rate and gives the
    registrar time to suspend the issuer.
    """

    scope = "issue"

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        org_id = getattr(request, "organization_id", None) or request.user.pk
        return self.cache_format % {"scope": self.scope, "ident": str(org_id)}


class ConfirmThrottle(AnonRateThrottle):
    """
    Caps guessing at credential confirmation tokens.

    The token is 256 bits, so brute force is hopeless on entropy alone; this
    exists so that an attacker working through a list cannot also use the
    endpoint as a free existence oracle at machine speed. Keyed on IP because
    the caller has, by definition, no account.
    """

    scope = "confirm"


class ConfirmResendThrottle(SimpleRateThrottle):
    """
    Caps re-sending a confirmation email.

    Without it, "resend" is a free mail-bomb aimed at whatever address the
    issuer names, delivered under the platform's own sending reputation. Keyed
    on the organisation rather than the IP: the abuse that matters is one issuer
    hammering many addresses, not many staff using one office connection.
    """

    scope = "confirm_resend"

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        org_id = getattr(request, "organization_id", None) or request.user.pk
        return self.cache_format % {"scope": self.scope, "ident": str(org_id)}
