"""Serializers for issuance and record display."""

from rest_framework import serializers

from apps.common.validators import UploadValidator

from .models import (
    AcademicDetail,
    BatchRowError,
    CredentialRecord,
    ExperienceDetail,
    IssuanceBatch,
    RecordType,
)


class AcademicDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicDetail
        fields = [
            "registration_number",
            "degree_title",
            "major",
            "level",
            "graduation_date",
            "graduation_date_bs",
            "cgpa",
            "percentage",
            "honours",
        ]


class ExperienceDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExperienceDetail
        fields = [
            "job_title",
            "department",
            "employment_type",
            "start_date",
            "end_date",
            "is_current",
            "departure_status",
            "responsibilities",
        ]

    def validate(self, attrs: dict) -> dict:
        # Mirrors the database CHECK constraint (E-06) so the client gets a
        # field-level message instead of a 500 from an IntegrityError.
        is_current = attrs.get("is_current", False)
        end_date = attrs.get("end_date")

        if is_current and end_date:
            raise serializers.ValidationError(
                {"end_date": "A current position cannot have an end date."}
            )
        if not is_current and not end_date:
            raise serializers.ValidationError(
                {"end_date": "An end date is required unless this is a current position."}
            )
        if end_date and attrs.get("start_date") and end_date < attrs["start_date"]:
            raise serializers.ValidationError(
                {"end_date": "The end date cannot be before the start date."}
            )
        return attrs


class AnchorSerializer(serializers.Serializer):
    """The chain evidence attached to a record — what makes a claim checkable."""

    state = serializers.CharField()
    tx_hash = serializers.CharField()
    block_number = serializers.IntegerField(allow_null=True)
    chain_id = serializers.IntegerField(allow_null=True)
    contract_address = serializers.CharField()
    issuer_address = serializers.CharField()
    confirmed_at = serializers.DateTimeField(allow_null=True)


class CredentialRecordSerializer(serializers.ModelSerializer):
    """Read representation of a record, with its typed detail inlined."""

    issuer_name = serializers.CharField(source="issuer.legal_name", read_only=True)
    issuer_kind = serializers.CharField(source="issuer.kind", read_only=True)
    issuer_status = serializers.CharField(source="issuer.status", read_only=True)
    detail = serializers.SerializerMethodField()
    anchor = serializers.SerializerMethodField()

    class Meta:
        model = CredentialRecord
        fields = [
            "id",
            "record_type",
            "status",
            "issuance_mode",
            "issuer",
            "issuer_name",
            "issuer_kind",
            "issuer_status",
            "subject_full_name",
            "subject_email",
            "record_hash",
            "document",
            "document_sha256",
            "detail",
            "anchor",
            "review_note",
            "issued_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_detail(self, record) -> dict:
        detail = record.detail
        if detail is None:
            return {}
        serializer = (
            ExperienceDetailSerializer
            if record.record_type == RecordType.EXPERIENCE
            else AcademicDetailSerializer
        )
        return serializer(detail).data

    def get_anchor(self, record) -> dict | None:
        anchor = (
            record.anchors.filter(tx_hash__gt="").order_by("-created_at").first()
            or record.anchors.order_by("-created_at").first()
        )
        return AnchorSerializer(anchor).data if anchor else None


class _BaseIssueSerializer(serializers.Serializer):
    """Shared fields for both authority-push issuance forms."""

    subject_full_name = serializers.CharField(max_length=150)
    subject_email = serializers.EmailField()
    document = serializers.FileField(required=False, validators=[UploadValidator()])

    # Optional, and an **attestation** rather than a lookup. The issuer already
    # holds this number on file to print the certificate at all, so supplying it
    # here is the organisation vouching for the holder's legal identity.
    #
    # Providing it raises the holder to IdentityLevel.CITIZENSHIP, which is what
    # later lets a verifier be told whether a genuine certificate really belongs
    # to the person they named. Omitting it is fine — the credential is still
    # fully verifiable, the subject-match question simply cannot be answered.
    #
    # Write-only: it is never echoed back in any response, and there is no
    # endpoint through which a *holder* can set their own.
    national_id = serializers.CharField(
        max_length=32, required=False, allow_blank=True, write_only=True
    )


class AcademicIssueSerializer(_BaseIssueSerializer):
    detail = AcademicDetailSerializer()

    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        validated["record_type"] = RecordType.ACADEMIC
        return validated


class ExperienceIssueSerializer(_BaseIssueSerializer):
    detail = ExperienceDetailSerializer()

    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        validated["record_type"] = RecordType.EXPERIENCE
        return validated


class ExperienceClaimSerializer(serializers.Serializer):
    """
    A seeker logging past employment for the employer to endorse (§6.2).

    The employer is chosen from approved organisations by id — free-text employer
    names would let a candidate "claim" a job at a company that has no way to
    dispute it, which is the exact fraud the platform exists to prevent.
    """

    employer = serializers.UUIDField()
    detail = ExperienceDetailSerializer()

    def validate_employer(self, value):
        from apps.organizations.models import Organization, OrganizationKind, OrganizationStatus

        employer = Organization.objects.filter(
            pk=value, kind=OrganizationKind.EMPLOYER, status=OrganizationStatus.APPROVED
        ).first()
        if employer is None:
            raise serializers.ValidationError(
                "No approved employer with this id. Ask them to register on the platform."
            )
        return employer


class ReviewSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class RejectSerializer(serializers.Serializer):
    # Mandatory here, unlike endorsement: a rejected claim without a reason gives
    # the seeker no way to correct an honest mistake (E-07).
    note = serializers.CharField(max_length=500)


class RevokeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class BatchRowErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchRowError
        fields = ["row_number", "raw_row", "error"]


class IssuanceBatchSerializer(serializers.ModelSerializer):
    errors = BatchRowErrorSerializer(many=True, read_only=True)

    class Meta:
        model = IssuanceBatch
        fields = [
            "id",
            "record_type",
            "source_filename",
            "status",
            "total_rows",
            "accepted_rows",
            "rejected_rows",
            "anchor_tx_hash",
            "errors",
            "created_at",
            "completed_at",
        ]
        read_only_fields = fields


class BatchUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    record_type = serializers.ChoiceField(choices=RecordType.choices)

    def validate_file(self, value):
        if not value.name.lower().endswith(".csv"):
            raise serializers.ValidationError("Upload a .csv file exported from your spreadsheet.")
        from django.conf import settings

        if value.size > settings.MAX_UPLOAD_SIZE_BYTES:
            raise serializers.ValidationError("The file is too large.")
        return value
