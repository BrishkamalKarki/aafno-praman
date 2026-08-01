from django.contrib import admin

from .models import ShareLink, ShareLinkRecord, VerificationLog


class ShareLinkRecordInline(admin.TabularInline):
    model = ShareLinkRecord
    extra = 0


@admin.register(ShareLink)
class ShareLinkAdmin(admin.ModelAdmin):
    list_display = ["__str__", "seeker", "include_all", "view_count", "expires_at", "revoked_at"]
    list_filter = ["include_all", "mask_identifiers"]
    search_fields = ["label", "seeker__user__email"]
    readonly_fields = ["id", "token", "view_count", "last_viewed_at", "created_at"]
    # passphrase_hash is excluded: there is no operational reason for staff to
    # see it, and displaying a hash invites offline cracking attempts.
    exclude = ["passphrase_hash"]
    inlines = [ShareLinkRecordInline]


@admin.register(VerificationLog)
class VerificationLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "result", "verifier_org", "record", "latency_ms"]
    list_filter = ["result", "counts_against_quota"]
    search_fields = ["record_hash", "lookup_reference"]
    readonly_fields = [f.name for f in VerificationLog._meta.fields]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
