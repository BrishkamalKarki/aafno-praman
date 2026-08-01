from django.contrib import admin

from .models import (
    AcademicDetail,
    BatchRowError,
    CredentialRecord,
    ExperienceDetail,
    IssuanceBatch,
)


class AcademicDetailInline(admin.StackedInline):
    model = AcademicDetail
    extra = 0


class ExperienceDetailInline(admin.StackedInline):
    model = ExperienceDetail
    extra = 0


@admin.register(CredentialRecord)
class CredentialRecordAdmin(admin.ModelAdmin):
    list_display = [
        "subject_full_name",
        "record_type",
        "issuer",
        "status",
        "short_hash",
        "issued_at",
    ]
    list_filter = ["record_type", "status", "issuance_mode", "issuer"]
    search_fields = ["subject_full_name", "subject_email", "record_hash"]
    readonly_fields = [
        "id",
        "record_hash",
        "canonical_payload",
        "dedupe_key",
        "document_sha256",
        "issued_at",
        "created_at",
        "updated_at",
    ]
    inlines = [AcademicDetailInline, ExperienceDetailInline]

    @admin.display(description="hash")
    def short_hash(self, obj) -> str:
        return f"{obj.record_hash[:12]}…" if obj.record_hash else "—"

    def has_delete_permission(self, request, obj=None):
        # An anchored record cannot be un-anchored, so deleting the off-chain row
        # would leave a chain entry no verifier could resolve. Revoke instead.
        return False


@admin.register(IssuanceBatch)
class IssuanceBatchAdmin(admin.ModelAdmin):
    list_display = [
        "source_filename",
        "organization",
        "status",
        "total_rows",
        "accepted_rows",
        "rejected_rows",
        "created_at",
    ]
    list_filter = ["status", "record_type"]
    search_fields = ["source_filename", "organization__legal_name"]
    readonly_fields = ["id", "anchor_tx_hash", "created_at", "completed_at"]


@admin.register(BatchRowError)
class BatchRowErrorAdmin(admin.ModelAdmin):
    list_display = ["batch", "row_number", "error"]
    search_fields = ["error"]
