"""
Registrar console.

Django admin serves as the platform registrar's workspace (HR-01). The approve /
suspend actions go through the same service functions as the API, so an approval
made here still generates the chain transaction and the audit entry — there is no
back door that writes a status field directly.
"""

from django.contrib import admin, messages

from .models import (
    IssuerKey,
    Organization,
    OrganizationDocument,
    OrganizationMembership,
    Subscription,
)
from .services import approve_organization, reinstate_organization, suspend_organization


class DocumentInline(admin.TabularInline):
    model = OrganizationDocument
    extra = 0
    readonly_fields = ["sha256", "created_at"]


class MembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0
    autocomplete_fields = ["user"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["legal_name", "kind", "status", "chain_address", "approved_at"]
    list_filter = ["status", "kind"]
    search_fields = ["legal_name", "registration_number", "contact_email", "chain_address"]
    readonly_fields = [
        "id",
        "slug",
        "chain_address",
        "approval_tx_hash",
        "approved_by",
        "approved_at",
        "approved_on_chain_at",
        "suspended_at",
        "created_at",
        "updated_at",
    ]
    inlines = [DocumentInline, MembershipInline]
    actions = ["approve_selected", "suspend_selected", "reinstate_selected"]

    @admin.action(description="Approve on chain (generates a signing key)")
    def approve_selected(self, request, queryset):
        for organization in queryset:
            try:
                approve_organization(organization, registrar=request.user, request=request)
                self.message_user(
                    request,
                    f"Approved {organization.legal_name} — {organization.chain_address}",
                    messages.SUCCESS,
                )
            except Exception as exc:
                self.message_user(request, f"{organization.legal_name}: {exc}", messages.ERROR)

    @admin.action(description="Suspend issuing rights")
    def suspend_selected(self, request, queryset):
        for organization in queryset:
            try:
                suspend_organization(
                    organization,
                    registrar=request.user,
                    reason="Suspended by registrar from the admin console.",
                    request=request,
                )
                self.message_user(request, f"Suspended {organization.legal_name}", messages.WARNING)
            except Exception as exc:
                self.message_user(request, f"{organization.legal_name}: {exc}", messages.ERROR)

    @admin.action(description="Reinstate issuing rights")
    def reinstate_selected(self, request, queryset):
        for organization in queryset:
            try:
                reinstate_organization(organization, registrar=request.user, request=request)
                self.message_user(
                    request, f"Reinstated {organization.legal_name}", messages.SUCCESS
                )
            except Exception as exc:
                self.message_user(request, f"{organization.legal_name}: {exc}", messages.ERROR)


@admin.register(IssuerKey)
class IssuerKeyAdmin(admin.ModelAdmin):
    """Read-only. Key material is never rendered, exported or editable."""

    list_display = ["organization", "address", "key_version", "last_used_at"]
    search_fields = ["organization__legal_name", "address"]
    readonly_fields = ["id", "organization", "address", "key_version", "last_used_at", "created_at"]
    exclude = ["encrypted_private_key"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Deleting a key orphans every record the organisation ever anchored.
        return False


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["organization", "plan", "monthly_lookup_limit", "started_at"]
    list_filter = ["plan"]
    search_fields = ["organization__legal_name"]
