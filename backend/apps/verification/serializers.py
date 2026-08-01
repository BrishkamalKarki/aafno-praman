"""Serializers for verification, the credential passport and share links."""

from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework import serializers

from apps.common.utils import mask_identifier
from apps.credentials.models import CredentialRecord, RecordType

from .models import ShareLink, ShareLinkRecord, VerificationLog


class VerificationOutcomeSerializer(serializers.Serializer):
    """
    The verification response.

    Shaped so a verifier can act on it without reading documentation: a machine
    ``result`` code, a human ``reason``, the record itself, and the chain evidence
    needed to check the claim independently.
    """

    result = serializers.CharField()
    reason = serializers.CharField()
    verified_at = serializers.DateTimeField(default=timezone.now)
    record = serializers.SerializerMethodField()
    issuer = serializers.DictField()
    chain = serializers.DictField()
    integrity = serializers.SerializerMethodField()
    latency_ms = serializers.IntegerField()

    def get_record(self, outcome) -> dict | None:
        if outcome.record is None:
            return None
        return SharedRecordSerializer(
            outcome.record, context={"mask": self.context.get("mask", False)}
        ).data

    def get_integrity(self, outcome) -> dict:
        """
        The two hashes, always both.

        Exposed even on success so a sceptical verifier can recompute the hash
        themselves from the returned record and confirm the platform is not
        simply asserting a green tick. On a TAMPERED result, the mismatch is the
        evidence.
        """
        return {
            "expected_hash": outcome.expected_hash,
            "computed_hash": outcome.computed_hash,
            "matches": bool(
                outcome.expected_hash and outcome.expected_hash == outcome.computed_hash
            ),
        }


class SharedRecordSerializer(serializers.ModelSerializer):
    """
    A record as shown to a verifier.

    Honours the ``mask`` flag from §6.3: registration and national ID numbers are
    masked to their last three characters, which is enough for a recruiter to
    confirm a number they were already given, and not enough to harvest one.
    """

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
            "subject_full_name",
            "issuer_name",
            "issuer_kind",
            "issuer_status",
            "record_hash",
            "detail",
            "anchor",
            "issued_at",
        ]
        read_only_fields = fields

    def get_detail(self, record) -> dict:
        from apps.credentials.serializers import (
            AcademicDetailSerializer,
            ExperienceDetailSerializer,
        )

        detail = record.detail
        if detail is None:
            return {}

        if record.record_type == RecordType.EXPERIENCE:
            return ExperienceDetailSerializer(detail).data

        data = AcademicDetailSerializer(detail).data
        if self.context.get("mask"):
            data["registration_number"] = mask_identifier(data.get("registration_number"))
        return data

    def get_anchor(self, record) -> dict | None:
        anchor = record.anchors.filter(tx_hash__gt="").order_by("-created_at").first()
        if anchor is None:
            return None
        return {
            "tx_hash": anchor.tx_hash,
            "block_number": anchor.block_number,
            "chain_id": anchor.chain_id,
            "contract_address": anchor.contract_address,
            "issuer_address": anchor.issuer_address,
            "confirmed_at": anchor.confirmed_at,
        }


class LookupSerializer(serializers.Serializer):
    reference = serializers.CharField(
        max_length=128,
        help_text="A record id or a 64-character record hash, as carried by a QR code.",
    )


class ShareLinkSerializer(serializers.ModelSerializer):
    url = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    requires_passphrase = serializers.BooleanField(read_only=True)
    record_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )
    passphrase = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=4
    )
    record_count = serializers.SerializerMethodField()

    class Meta:
        model = ShareLink
        fields = [
            "id",
            "token",
            "url",
            "label",
            "include_all",
            "mask_identifiers",
            "expires_at",
            "max_views",
            "view_count",
            "last_viewed_at",
            "revoked_at",
            "is_active",
            "requires_passphrase",
            "record_ids",
            "passphrase",
            "record_count",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "token",
            "url",
            "view_count",
            "last_viewed_at",
            "revoked_at",
            "created_at",
        ]

    def get_record_count(self, link) -> int:
        if link.include_all:
            return link.seeker.records.filter(status="ISSUED").count()
        return link.selections.count()

    def validate_expires_at(self, value):
        if value and value <= timezone.now():
            raise serializers.ValidationError("The expiry must be in the future.")
        return value

    def validate(self, attrs: dict) -> dict:
        if not attrs.get("include_all", True) and not attrs.get("record_ids"):
            raise serializers.ValidationError(
                {"record_ids": "Select at least one record, or set include_all to true."}
            )
        return attrs

    def create(self, validated_data: dict) -> ShareLink:
        record_ids = validated_data.pop("record_ids", [])
        passphrase = validated_data.pop("passphrase", "")
        seeker = self.context["request"].user.seeker_profile

        if passphrase:
            # Hashed with Django's password hasher rather than compared in plain
            # text, so a database leak does not hand out access to every
            # protected link.
            validated_data["passphrase_hash"] = make_password(passphrase)

        link = ShareLink.objects.create(seeker=seeker, **validated_data)

        if not link.include_all and record_ids:
            # Filtered by owner: a seeker must not be able to publish someone
            # else's records by pasting their record ids.
            owned = CredentialRecord.objects.filter(id__in=record_ids, subject=seeker)
            ShareLinkRecord.objects.bulk_create(
                [ShareLinkRecord(share_link=link, record=record) for record in owned]
            )
        return link


class SharedPassportSerializer(serializers.Serializer):
    """The public view behind a share link."""

    owner_name = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    shared_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField(allow_null=True)
    masked = serializers.BooleanField()
    summary = serializers.DictField()
    records = serializers.ListField(child=serializers.DictField())


class UnlockSerializer(serializers.Serializer):
    passphrase = serializers.CharField(max_length=128)


class VerificationLogSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="record.subject_full_name", read_only=True)
    issuer_name = serializers.CharField(source="record.issuer.legal_name", read_only=True)

    class Meta:
        model = VerificationLog
        fields = [
            "id",
            "result",
            "record",
            "subject_name",
            "issuer_name",
            "lookup_reference",
            "latency_ms",
            "counts_against_quota",
            "created_at",
        ]
        read_only_fields = fields


class CandidateSerializer(serializers.Serializer):
    """
    A discoverable candidate in employer search (§5.3).

    Only ever populated from profiles where ``is_discoverable`` is true, and it
    exposes no contact details — an employer can see verified qualifications and
    request contact through the platform, not scrape a mailing list.
    """

    id = serializers.UUIDField()
    full_name = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    public_slug = serializers.CharField()
    verified_academic_count = serializers.IntegerField()
    verified_experience_count = serializers.IntegerField()
    highest_qualification = serializers.CharField(allow_blank=True)
