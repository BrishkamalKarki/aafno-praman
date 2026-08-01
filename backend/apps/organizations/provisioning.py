"""
Registrar-driven account provisioning.

The admin console has no self-registration: a registrar fills in a form on the
person's or organisation's behalf and hands over a temporary password out of
band. That is the flow the three ``/admin/create/*`` screens describe, and this
module is the API behind them.

Two endpoints, mirroring the two things that get created:

* ``ProvisionSeekerView``       — a citizen account with a credential passport.
* ``ProvisionOrganizationView`` — an institution or employer, approved and
  registered on chain in the same call, plus its first (owner) staff account.

Both return the generated password exactly once, in the response body. It is
hashed like any other password and is not retrievable again; showing it here is
the only delivery channel this MVP has, and saying so is better than pretending
there is a reset email that nobody has configured.
"""

from __future__ import annotations

import secrets
import string

from django.db import transaction
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.accounts.serializers import UserSerializer
from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.common.permissions import IsRegistrar

from .models import MembershipRole, Organization, OrganizationKind, OrganizationMembership
from .serializers import OrganizationSerializer
from .services import approve_organization

#: No look-alike characters. The registrar reads this down a phone line or
#: copies it into a chat message; `l` versus `1` is a support ticket.
_PASSWORD_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "lI1O0")


def generate_temp_password(length: int = 12) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def _unique_org_slug(name: str) -> str:
    base = slugify(name)[:60] or "org"
    slug = base
    suffix = 2
    while Organization.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


class ProvisionSeekerSerializer(serializers.Serializer):
    """
    Create a citizen account.

    Deliberately narrow: the citizenship number is accepted by the *form* but
    not persisted here. Per ``SeekerProfile``'s identity model it may only ever
    be set by an approved issuer attesting to a number it already holds on file
    — taking it as free text from an admin screen would make the CITIZENSHIP
    identity level self-asserted, which is precisely what it exists to rule out.
    """

    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    @transaction.atomic
    def create(self, validated_data: dict) -> dict:
        password = generate_temp_password()
        date_of_birth = validated_data.get("date_of_birth")

        user = User.objects.create_user(
            email=validated_data["email"],
            full_name=validated_data["full_name"],
            phone=validated_data.get("phone", ""),
            role=Role.SEEKER,
            password=password,
        )

        # The passport itself is created by the post_save signal, so this only
        # fills in what the form collected on top of it.
        if date_of_birth is not None:
            profile = user.seeker_profile
            profile.date_of_birth = date_of_birth
            profile.save(update_fields=["date_of_birth"])

        return {"user": user, "temp_password": password}


class ProvisionOrganizationSerializer(serializers.Serializer):
    """
    Create an organisation and approve it in one call.

    Registrar-provisioned organisations skip the PENDING queue because the
    registrar's off-platform diligence already happened before they opened this
    form. The self-service ``organizations/apply/`` path is untouched and still
    lands in PENDING for separate review — this is a second door for the same
    room, not a way around the gate.
    """

    kind = serializers.ChoiceField(choices=OrganizationKind.choices)
    legal_name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    registration_number = serializers.CharField(max_length=64)
    contact_person = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)

    def validate(self, attrs: dict) -> dict:
        email = attrs["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                {"email": "An account with this email already exists."}
            )

        registration_number = attrs["registration_number"].strip()
        if Organization.objects.filter(
            kind=attrs["kind"], registration_number=registration_number
        ).exists():
            raise serializers.ValidationError(
                {
                    "registration_number": (
                        "An organisation with this registration number already exists."
                    )
                }
            )

        attrs["email"] = email
        attrs["registration_number"] = registration_number
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict) -> dict:
        request = self.context["request"]
        registrar = request.user
        password = generate_temp_password()

        organization = Organization.objects.create(
            kind=validated_data["kind"],
            legal_name=validated_data["legal_name"],
            slug=_unique_org_slug(validated_data["legal_name"]),
            registration_number=validated_data["registration_number"],
            contact_email=validated_data["email"],
            contact_phone=validated_data.get("phone", ""),
            address=validated_data.get("address", ""),
            website=validated_data.get("website", ""),
        )

        owner = User.objects.create_user(
            email=validated_data["email"],
            full_name=validated_data.get("contact_person") or validated_data["legal_name"],
            phone=validated_data.get("phone", ""),
            role=Role.ORG_MEMBER,
            password=password,
        )
        OrganizationMembership.objects.create(
            user=owner, organization=organization, role=MembershipRole.OWNER
        )

        record_event(
            AuditAction.ORG_APPLIED,
            actor=registrar,
            organization=organization,
            obj=organization,
            metadata={"kind": organization.kind, "provisioned_by_registrar": True},
            request=request,
        )

        # Chain-first, using the same service the registrar console's own
        # "approve" action uses. If the ledger is unreachable this raises and the
        # whole transaction — organisation, owner account, membership — rolls
        # back, so the registrar retries one form instead of cleaning up a
        # half-created account by hand.
        approve_organization(organization, registrar=registrar, request=request)
        organization.refresh_from_db()

        return {"user": owner, "organization": organization, "temp_password": password}


class _ProvisionView(APIView):
    permission_classes = [IsAuthenticated, IsRegistrar]
    serializer_class: type[serializers.Serializer]

    def post(self, request):
        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(self.represent(result), status=status.HTTP_201_CREATED)

    def represent(self, result: dict) -> dict:  # pragma: no cover - overridden
        raise NotImplementedError


@extend_schema(
    tags=["registrar"],
    summary="Create a citizen account",
    request=ProvisionSeekerSerializer,
    responses={
        201: inline_serializer(
            name="ProvisionedSeeker",
            fields={
                "user": UserSerializer(),
                "temp_password": serializers.CharField(),
            },
        )
    },
)
class ProvisionSeekerView(_ProvisionView):
    serializer_class = ProvisionSeekerSerializer

    def represent(self, result: dict) -> dict:
        return {
            "user": UserSerializer(result["user"]).data,
            "temp_password": result["temp_password"],
        }


@extend_schema(
    tags=["registrar"],
    summary="Create and approve an institution or employer",
    request=ProvisionOrganizationSerializer,
    responses={
        201: inline_serializer(
            name="ProvisionedOrganization",
            fields={
                "user": UserSerializer(),
                "organization": OrganizationSerializer(),
                "temp_password": serializers.CharField(),
            },
        )
    },
)
class ProvisionOrganizationView(_ProvisionView):
    serializer_class = ProvisionOrganizationSerializer

    def represent(self, result: dict) -> dict:
        return {
            "user": UserSerializer(result["user"]).data,
            "organization": OrganizationSerializer(result["organization"]).data,
            "temp_password": result["temp_password"],
        }
