from django.contrib import admin

from .models import LedgerAnchor, RevocationEvent


@admin.register(LedgerAnchor)
class LedgerAnchorAdmin(admin.ModelAdmin):
    list_display = ["short_hash", "state", "tx_hash", "block_number", "attempts", "confirmed_at"]
    list_filter = ["state"]
    search_fields = ["record_hash", "tx_hash", "issuer_address"]
    readonly_fields = [f.name for f in LedgerAnchor._meta.fields]

    @admin.display(description="record hash")
    def short_hash(self, obj) -> str:
        return f"{obj.record_hash[:16]}…"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Anchors mirror chain state. Editing one here would make the database
        # disagree with the ledger, which is the one thing this table must not do.
        return False


@admin.register(RevocationEvent)
class RevocationEventAdmin(admin.ModelAdmin):
    list_display = ["record", "reason", "revoked_by", "confirmed_on_chain", "created_at"]
    list_filter = ["confirmed_on_chain"]
    search_fields = ["reason", "tx_hash"]
    readonly_fields = ["id", "created_at", "updated_at"]
