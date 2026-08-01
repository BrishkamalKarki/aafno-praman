"""Serializers for organisation onboarding and self-service."""

from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers

from apps.common.utils import sha256_file

from .models import (
    MembershipRole,
    Organization,
    OrganizationDocument,
    OrganizationMembership,
    Plan,
    Subscription,
)


class OrganizationDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationDocument
        fields = ["id", "doc_type", "file", "sha256", "created_at"]
        read_only_fields = ["id", "sha256", "created_at"]

    def create(self, validated_data):
        validated_data["sha256"] = sha256_file(validated_data["file"])
        return super().create(validated_data)


class OrganizationSerializer(serializers.ModelSerializer):
    """Public/self view of an organisation."""

    can_issue = serializers.BooleanField(read_only=True)
    documents = OrganizationDocumentSerializer(many=True, read_only=True)
    member_count = serializers.SerializerMethodField()
    plan = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id",
            "kind",
            "legal_name",
            "slug",
            "registration_number",
            "website",
            "contact_email",
            "contact_phone",
            "address",
            "status",
            "status_reason",
            "chain_address",
            "approval_tx_hash",
            "approved_at",
            "can_issue",
            "documents",
            "member_count",
            "plan",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "status",
            "status_reason",
            "chain_address",
            "approval_tx_hash",
            "approved_at",
            "can_issue",
            "created_at",
        ]

    def get_member_count(self, org) -> int:
        return org.memberships.count()

    def get_plan(self, org) -> str:
        subscription = getattr(org, "subscription", None)
        return subscription.plan if subscription else "FREE"


class OrganizationDirectorySerializer(serializers.ModelSerializer):
    """
    An organisation as a name to pick from a list.

    Everything identifying beyond the name and kind is left out on purpose —
    see ``OrganizationDirectoryView`` for what this exists for and what it must
    not become.
    """

    class Meta:
        model = Organization
        fields = ["id", "legal_name", "kind", "slug"]
        read_only_fields = fields


class OrganizationApplicationSerializer(serializers.ModelSerializer):
    """
    Apply to become an issuer.

    Creates the organisation in ``PENDING`` and makes the applicant its OWNER.
    Status and chain address are absent from the writable fields on purpose:
    self-approval would make the entire root-of-trust model decorative.
    """

    class Meta:
        model = Organization
        fields = [
            "id",
            "kind",
            "legal_name",
            "registration_number",
            "website",
            "contact_email",
            "contact_phone",
            "address",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: dict) -> dict:
        kind = attrs["kind"]
        registration_number = attrs["registration_number"].strip()
        if Organization.objects.filter(kind=kind, registration_number=registration_number).exists():
            raise serializers.ValidationError(
                {
                    "registration_number": (
                        "An organisation with this registration number already exists. "
                        "Ask its owner to invite you instead of applying again."
                    )
                }
            )
        attrs["registration_number"] = registration_number
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict) -> Organization:
        user = self.context["request"].user
        validated_data["slug"] = _unique_slug(validated_data["legal_name"])
        organization = Organization.objects.create(**validated_data)

        OrganizationMembership.objects.create(
            user=user, organization=organization, role=MembershipRole.OWNER
        )
        # The applicant becomes an organisation member; a seeker account that
        # applies keeps its passport, since a person can genuinely be both.
        from apps.accounts.models import Role

        if (
            user.role == Role.SEEKER
            and not user.memberships.exclude(organization=organization).exists()
        ):
            user.role = Role.ORG_MEMBER
            user.save(update_fields=["role"])

        return organization


class RegistrarOrganizationSerializer(OrganizationSerializer):
    """Registrar view — adds the review context the platform staff need."""

    applicant = serializers.SerializerMethodField()
    issued_count = serializers.SerializerMethodField()

    class Meta(OrganizationSerializer.Meta):
        fields = OrganizationSerializer.Meta.fields + ["applicant", "issued_count"]

    def get_applicant(self, org) -> dict:
        owner = org.memberships.filter(role=MembershipRole.OWNER).select_related("user").first()
        if owner is None:
            return {}
        return {"email": owner.user.email, "full_name": owner.user.full_name}

    def get_issued_count(self, org) -> int:
        return org.issued_records.count()


class MembershipSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = ["id", "email", "full_name", "role", "created_at"]
        read_only_fields = ["id", "created_at"]


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ["plan", "monthly_lookup_limit", "started_at"]
        read_only_fields = ["started_at"]


class PlanChangeSerializer(serializers.Serializer):
    """Demo-mode plan switch — see ``SubscriptionView.patch`` for what is missing."""

    plan = serializers.ChoiceField(choices=Plan.choices)


class StatusChangeSerializer(serializers.Serializer):
    """Payload for reject/suspend — a reason is mandatory."""

    reason = serializers.CharField(
        max_length=500,
        # Required because an organisation told only "suspended" has no way to
        # fix the problem, and because the audit trail needs the justification.
        help_text="Shown to the organisation and recorded in the audit log.",
    )


def _unique_slug(name: str) -> str:
    base = slugify(name)[:60] or "org"
    slug = base
    suffix = 2
    while Organization.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug
