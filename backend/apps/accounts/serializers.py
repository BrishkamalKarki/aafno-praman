"""Serializers for registration, login and profile."""

from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .identity import mask_national_id
from .models import Role, SeekerProfile, User


def _decorate(token, user):
    """
    Attach display claims to a token.

    Deliberately excluded: anything the server uses to *authorise*. Roles,
    organisation approval and identity level are re-read from the database on
    every request, so a token minted before an issuer was suspended grants
    nothing afterwards.
    """
    token["email"] = user.email
    token["full_name"] = user.full_name
    token["role"] = user.role
    return token


def issue_token_pair(user) -> dict:
    """Mint an access/refresh pair for a user authenticated by any means."""
    refresh = RefreshToken.for_user(user)
    _decorate(refresh, user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class TokenObtainSerializer(TokenObtainPairSerializer):
    """Password login — organisation staff and registrars only."""

    @classmethod
    def get_token(cls, user):
        return _decorate(super().get_token(user), user)

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class UserSerializer(serializers.ModelSerializer):
    organizations = serializers.SerializerMethodField()
    passport_slug = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "phone",
            "role",
            "date_joined",
            "organizations",
            "passport_slug",
        ]
        read_only_fields = ["id", "email", "role", "date_joined"]

    def get_organizations(self, user) -> list:
        return [
            {
                "id": str(m.organization_id),
                "slug": m.organization.slug,
                "name": m.organization.legal_name,
                "kind": m.organization.kind,
                "status": m.organization.status,
                "role": m.role,
                "can_issue": m.can_issue,
            }
            for m in user.memberships.select_related("organization").all()
        ]

    def get_passport_slug(self, user) -> str:
        profile = getattr(user, "seeker_profile", None)
        return profile.public_slug if profile else ""


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["email", "full_name", "phone", "password", "password_confirm", "role"]
        extra_kwargs = {"role": {"required": False}}

    def validate_email(self, value: str) -> str:
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            # Registration cannot avoid disclosing that an address is taken — the
            # alternative is silently failing to create the account. Login and
            # password reset stay deliberately non-committal instead.
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_role(self, value: str) -> str:
        # REGISTRAR is created only via `manage.py createsuperuser`. Accepting it
        # from a request body would make the platform's root of trust
        # self-service, which is the whole vulnerability the role exists to close.
        if value == Role.REGISTRAR:
            raise serializers.ValidationError("This role cannot be self-assigned.")
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})

        temp = User(
            email=attrs.get("email", ""),
            full_name=attrs.get("full_name", ""),
            role=attrs.get("role", Role.SEEKER),
        )
        validate_password(attrs["password"], temp)
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict) -> User:
        password = validated_data.pop("password")
        validated_data.setdefault("role", Role.SEEKER)
        return User.objects.create_user(password=password, **validated_data)


class SeekerProfileSerializer(serializers.ModelSerializer):
    """
    The citizen's own view of their identity.

    ``national_id`` is not writable here, and never will be. It was previously,
    which meant a holder could assert any citizenship number they liked and the
    platform would believe them. It is now set only by the approved issuer that
    already holds it on file — self-assertion is exactly what would make the
    CITIZENSHIP identity level meaningless.

    ``legal_name`` is likewise read-only: it is part of the hashed payload of
    every credential issued to this account, so letting the subject edit it
    would invalidate their own degrees.
    """

    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    passport_url = serializers.CharField(read_only=True)
    national_id_masked = serializers.SerializerMethodField()
    citizenship_verified_by_name = serializers.CharField(
        source="citizenship_verified_by.legal_name", read_only=True, default=""
    )

    class Meta:
        model = SeekerProfile
        fields = [
            "id",
            "email",
            "phone",
            "legal_name",
            "public_slug",
            "passport_url",
            "national_id_masked",
            "identity_level",
            "citizenship_verified_by_name",
            "citizenship_verified_at",
            "headline",
            "date_of_birth",
            "is_discoverable",
        ]
        # Everything identity-bearing is immutable through this endpoint. What a
        # citizen may edit is exactly: how to contact them, how they describe
        # themselves, and whether employers may find them.
        read_only_fields = [
            "id",
            "email",
            "phone",
            "legal_name",
            "public_slug",
            "passport_url",
            "national_id_masked",
            "identity_level",
            "citizenship_verified_by_name",
            "citizenship_verified_at",
        ]

    def get_national_id_masked(self, identity) -> str:
        """
        Show the tail of the citizenship number so the owner can confirm the
        platform holds the right one — without the platform handing it back.

        Requires a decrypt, so it is computed only for this single-object
        endpoint and never for a list.
        """
        from .identity import IdentityError, decrypt_national_id

        try:
            return mask_national_id(decrypt_national_id(identity.national_id_ct))
        except IdentityError:
            return ""


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value: str) -> str:
        validate_password(value, self.context["request"].user)
        return value

    def save(self, **kwargs) -> User:
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
