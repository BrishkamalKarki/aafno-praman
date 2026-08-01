"""
Permission classes.

Authority to act is always derived from live state — an organisation's current
status and the user's membership row — never from a value copied onto the user or
baked into a token. Suspending an issuer therefore takes effect on the very next
request, with no cache to invalidate and no session to expire.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.common.exceptions import IssuerNotApproved


class IsRegistrar(BasePermission):
    """Platform staff — the root of trust that onboards issuers (HR-01)."""

    message = "Only the platform registrar can perform this action."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and (user.is_registrar or user.is_superuser))


class IsCitizen(BasePermission):
    """
    A credential-holding account.

    Authentication alone is not enough. Every role on this platform signs in the
    same way — email and password — so "is authenticated" spans citizens,
    organisation staff and registrars alike, and treating it as sufficient would
    let an employer's receptionist read a citizen's passport endpoints.

    The role and the profile are read from the database on every request rather
    than trusted from the token, so a role change takes effect on the next call
    with no session to expire.

    Sets ``request.identity`` so views do not each repeat the lookup.
    """

    message = "Only a credential holder can perform this action."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_seeker):
            return False

        identity = getattr(user, "seeker_profile", None)
        if identity is None:
            return False

        request.identity = identity
        return True


class IsOrganizationMember(BasePermission):
    """
    Membership of any organisation, in any role.

    Sets ``request.membership`` and ``request.organization`` so views and the
    issuance throttle do not each re-run the lookup.
    """

    message = "You must belong to an organisation to access this."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False

        membership = user.memberships.select_related("organization").order_by("created_at").first()
        if membership is None:
            return False

        request.membership = membership
        request.organization = membership.organization
        request.organization_id = membership.organization_id
        return True


class CanIssueCredentials(IsOrganizationMember):
    """
    Membership *and* an approved organisation *and* an issuing role.

    Raises rather than returning False when the only thing missing is approval:
    "you are not approved yet" is actionable, whereas a bare 403 sends a
    university's IT office hunting for a bug that does not exist.
    """

    message = "Your role does not permit issuing records."

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False

        membership = request.membership
        if not membership.organization.can_issue:
            raise IssuerNotApproved()

        from apps.organizations.models import MembershipRole

        return membership.role in {MembershipRole.OWNER, MembershipRole.ISSUER}


class IsInstitution(CanIssueCredentials):
    """Academic credentials may only be issued by institutions."""

    # Set only when the *kind* check is the one that fails. Overriding `message`
    # at class level would relabel every parent failure too, so a VIEWER at a
    # university would be told their university is not an institution — sending
    # them to fix something that is not broken.
    kind_message = "Only educational institutions can issue academic credentials."

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        from apps.organizations.models import OrganizationKind

        if request.organization.kind != OrganizationKind.INSTITUTION:
            self.message = self.kind_message
            return False
        return True


class IsEmployer(CanIssueCredentials):
    """Experience records may only be issued by employers."""

    kind_message = "Only employers can issue work experience records."

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        from apps.organizations.models import OrganizationKind

        if request.organization.kind != OrganizationKind.EMPLOYER:
            self.message = self.kind_message
            return False
        return True


class IsRecordIssuerOrReadOnly(BasePermission):
    """Object-level guard: only the issuing organisation may modify a record."""

    message = "Only the issuing organisation can modify this record."

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        organization = getattr(request, "organization", None)
        return organization is not None and obj.issuer_id == organization.pk


class IsSubjectOfRecord(BasePermission):
    """Object-level guard for passport operations: the seeker owns the record."""

    message = "This record does not belong to you."

    def has_object_permission(self, request, view, obj) -> bool:
        profile = getattr(request.user, "seeker_profile", None)
        if profile is None:
            return False
        subject_id = getattr(obj, "subject_id", None) or getattr(obj, "seeker_id", None)
        return subject_id == profile.pk
