from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """
    Strictly read-only.

    An audit trail that platform staff can edit or delete is not evidence, so
    every mutation permission is denied — including for superusers.
    """

    list_display = ["created_at", "action", "actor_label", "organization", "object_type"]
    list_filter = ["action", "created_at"]
    search_fields = ["actor_label", "object_id", "action"]
    readonly_fields = [f.name for f in AuditEvent._meta.fields]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
