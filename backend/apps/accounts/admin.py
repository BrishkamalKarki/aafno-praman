from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import SeekerProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["email", "full_name", "role", "is_active", "is_staff", "date_joined"]
    list_filter = ["role", "is_active", "is_staff"]
    search_fields = ["email", "full_name"]
    readonly_fields = ["id", "date_joined", "last_login"]

    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        ("Identity", {"fields": ("full_name", "phone", "role")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "password1", "password2"),
            },
        ),
    )


@admin.register(SeekerProfile)
class SeekerProfileAdmin(admin.ModelAdmin):
    """
    Citizen identities.

    Nothing here exposes a citizenship number, in any column, filter or search
    box. ``national_id_hmac`` is not searchable either: a registrar who could
    paste a number and find its owner would be a working enumeration oracle
    wearing an admin login, which is the exact capability the HMAC exists to
    deny. Resolving a number to a person is a deliberate, logged operation via
    ``apps.accounts.identity``, not a text field.
    """

    list_display = ["legal_name", "user", "identity_level", "is_discoverable", "created_at"]
    list_filter = ["identity_level", "is_discoverable"]
    search_fields = ["legal_name", "public_slug", "user__email"]
    readonly_fields = [
        "id",
        "public_slug",
        "national_id_hmac",
        "hmac_version",
        "identity_level",
        "citizenship_verified_by",
        "citizenship_verified_at",
        "created_at",
        "updated_at",
    ]
    exclude = ["national_id_ct"]
