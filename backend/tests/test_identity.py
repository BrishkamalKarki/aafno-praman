"""
Citizen identity: normalisation, peppered hashing, salted on-chain bindings.

These tests guard the two properties the whole privacy model rests on:

1. One real person resolves to exactly one identity, however their citizenship
   number happens to be written down.
2. Nothing derived from a citizenship number is usable to work backwards to a
   person — not the lookup hash, and especially not the value that reaches the
   public ledger.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.accounts import identity as idc
from apps.accounts.models import IdentityLevel, Role, SeekerProfile, User
from apps.accounts.services import (
    CitizenshipConflict,
    attest_citizenship,
    get_or_create_account,
    profile_for_national_id,
)
from apps.common.exceptions import ConflictError

from .conftest import NATIONAL_ID


class TestNormalisation:
    @pytest.mark.parametrize(
        "written",
        ["12-01-70-98765", "12/01/70/98765", "12 01 70 98765", "12017098765", " 12017098765 "],
        ids=["dashes", "slashes", "spaces", "bare", "padded"],
    )
    def test_written_forms_collapse_to_one_identity(self, written):
        """
        Registrars' offices write citizenship numbers inconsistently. If these
        did not collapse, one citizen would end up with several identities and a
        degree in whichever one they cannot sign into.
        """
        assert idc.national_id_hmac(written) == idc.national_id_hmac(NATIONAL_ID)

    def test_distinct_numbers_do_not_collide(self):
        assert idc.national_id_hmac("12017098765") != idc.national_id_hmac("12017098766")

    @pytest.mark.parametrize(
        "bad", ["", None, "abc", "12", "1" * 21], ids=["empty", "none", "letters", "short", "long"]
    )
    def test_unusable_input_raises_rather_than_normalising_to_empty(self, bad):
        """
        Returning "" for junk would make every unparseable value collide into a
        single shared identity under the unique constraint.
        """
        with pytest.raises(idc.IdentityError):
            idc.national_id_hmac(bad)

    def test_hash_depends_on_the_pepper(self, settings):
        before = idc.national_id_hmac(NATIONAL_ID)
        settings.NATIONAL_ID_PEPPER = "a-different-pepper-entirely"
        assert idc.national_id_hmac(NATIONAL_ID) != before

    def test_missing_pepper_is_a_loud_failure(self, settings):
        settings.NATIONAL_ID_PEPPER = ""
        with pytest.raises(idc.IdentityError, match="NATIONAL_ID_PEPPER"):
            idc.national_id_hmac(NATIONAL_ID)


class TestSubjectBinding:
    """
    The value that reaches the chain.

    Anchors are permanent and public. If a pepper leak ever let someone
    correlate on-chain bindings back to citizens, there would be no remediation
    available — the data cannot be withdrawn. Per-record salt is what bounds that
    blast radius to nothing.
    """

    def test_same_citizen_produces_unlinkable_bindings_across_records(self):
        a = idc.subject_binding(NATIONAL_ID, idc.new_binding_salt())
        b = idc.subject_binding(NATIONAL_ID, idc.new_binding_salt())
        assert a != b

    def test_binding_is_deterministic_for_a_fixed_salt(self):
        salt = idc.new_binding_salt()
        assert idc.subject_binding(NATIONAL_ID, salt) == idc.subject_binding(NATIONAL_ID, salt)

    def test_correct_citizen_matches(self):
        salt = idc.new_binding_salt()
        assert idc.binding_matches(NATIONAL_ID, salt, idc.subject_binding(NATIONAL_ID, salt))

    def test_different_citizen_does_not_match(self):
        salt = idc.new_binding_salt()
        binding = idc.subject_binding(NATIONAL_ID, salt)
        assert not idc.binding_matches("12017000001", salt, binding)

    def test_binding_does_not_verify_under_a_different_salt(self):
        binding = idc.subject_binding(NATIONAL_ID, idc.new_binding_salt())
        assert not idc.binding_matches(NATIONAL_ID, idc.new_binding_salt(), binding)

    def test_salt_is_long_enough_to_be_unguessable(self):
        assert len(bytes.fromhex(idc.new_binding_salt())) == idc.BINDING_SALT_BYTES >= 16

    @pytest.mark.parametrize(
        "salt,expected", [("", "abc"), ("aabb", "")], ids=["no_salt", "no_binding"]
    )
    def test_missing_inputs_never_report_a_match(self, salt, expected):
        assert not idc.binding_matches(NATIONAL_ID, salt, expected)

    def test_malformed_citizen_input_never_reports_a_match(self):
        salt = idc.new_binding_salt()
        assert not idc.binding_matches("not-a-number", salt, idc.subject_binding(NATIONAL_ID, salt))


class TestEncryptionAtRest:
    def test_round_trips_to_the_normalised_digits(self):
        assert idc.decrypt_national_id(idc.encrypt_national_id(NATIONAL_ID)) == "12017098765"

    def test_ciphertext_does_not_contain_the_plaintext(self):
        assert b"12017098765" not in bytes(idc.encrypt_national_id(NATIONAL_ID))

    def test_encryption_is_non_deterministic(self):
        """Fernet includes a random IV, so equal numbers must not yield equal blobs."""
        assert idc.encrypt_national_id(NATIONAL_ID) != idc.encrypt_national_id(NATIONAL_ID)

    def test_empty_ciphertext_decrypts_to_empty(self):
        assert idc.decrypt_national_id(None) == ""
        assert idc.decrypt_national_id(b"") == ""

    def test_wrong_key_is_a_loud_failure(self, settings):
        blob = idc.encrypt_national_id(NATIONAL_ID)
        settings.KEY_ENCRYPTION_KEY = "59haqcq4uQ6ua38xWGJQQhtd8z2alQCMmhFXKx10W2Y="
        with pytest.raises(idc.IdentityError, match="KEY_ENCRYPTION_KEY"):
            idc.decrypt_national_id(blob)


class TestMasking:
    def test_keeps_only_the_tail(self):
        assert idc.mask_national_id("12017098765") == "•••••••8765"

    def test_leaks_no_leading_digits(self):
        assert "1201" not in idc.mask_national_id("12017098765")

    def test_short_values_are_fully_masked(self):
        assert idc.mask_national_id("123") == "•••"

    def test_empty_stays_empty(self):
        assert idc.mask_national_id("") == ""
        assert idc.mask_national_id(None) == ""


@pytest.mark.django_db
class TestAccountProvisioning:
    def test_creates_an_email_only_account(self, institution):
        profile, created = get_or_create_account(email="Ram@Example.COM", full_name="Ram Thapa")
        assert created
        assert profile.user.email == "ram@example.com"
        assert profile.identity_level == IdentityLevel.EMAIL_ONLY
        assert profile.has_citizenship is False

    def test_account_starts_without_a_usable_password(self):
        """
        Issuance creates the account before the person has ever visited. Giving
        it a password would invent a credential nobody asked for and nobody can
        rotate; they activate it by confirming the emailed link.
        """
        profile, _ = get_or_create_account(email="new@example.com")
        assert not profile.user.has_usable_password()

    def test_is_idempotent_on_email(self):
        first, _ = get_or_create_account(email="ram@example.com", full_name="Ram Thapa")
        second, created = get_or_create_account(email="RAM@example.com")
        assert not created
        assert second.pk == first.pk

    def test_a_later_issuer_cannot_rewrite_an_existing_name(self, holder):
        """Otherwise any approved issuer could rewrite any holder's identity."""
        again, _ = get_or_create_account(email="sita@example.com", full_name="Someone Else")
        assert again.legal_name == "Sita Sharma"

    def test_organisation_accounts_are_not_turned_into_holders(self):
        staff = User.objects.create_user(
            email="hr@leapfrog.com.np",
            password="a-long-password-1",
            full_name="HR",
            role=Role.ORG_MEMBER,
        )
        assert staff.role == Role.ORG_MEMBER
        with pytest.raises(ConflictError):
            get_or_create_account(email="hr@leapfrog.com.np")

    def test_registering_creates_a_passport_automatically(self):
        user = User.objects.create_user(
            email="self@example.com", password="a-long-password-1", full_name="Self Signup"
        )
        assert SeekerProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
class TestCitizenshipAttestation:
    def test_raises_identity_level_when_an_issuer_attests(self, holder, institution):
        attest_citizenship(profile=holder, national_id=NATIONAL_ID, organization=institution)
        holder.refresh_from_db()
        assert holder.identity_level == IdentityLevel.CITIZENSHIP
        assert holder.has_citizenship
        assert holder.citizenship_verified_by_id == institution.pk

    def test_is_idempotent_across_written_forms(self, holder, institution):
        attest_citizenship(profile=holder, national_id="12-01-70-98765", organization=institution)
        attest_citizenship(profile=holder, national_id="12/01/70/98765", organization=institution)
        holder.refresh_from_db()
        assert holder.identity_level == IdentityLevel.CITIZENSHIP

    def test_number_cannot_be_shared_by_two_accounts(self, holder, institution):
        attest_citizenship(profile=holder, national_id=NATIONAL_ID, organization=institution)
        other, _ = get_or_create_account(email="impostor@example.com")
        with pytest.raises(CitizenshipConflict):
            attest_citizenship(profile=other, national_id=NATIONAL_ID, organization=institution)

    def test_changing_an_attested_number_requires_registrar_review(self, holder, institution):
        """
        A silent overwrite would let a second issuer hijack the subject-match
        guarantee the first one established.
        """
        attest_citizenship(profile=holder, national_id=NATIONAL_ID, organization=institution)
        with pytest.raises(ConflictError):
            attest_citizenship(
                profile=holder, national_id="99-88-77-66655", organization=institution
            )

    def test_lookup_resolves_only_for_attested_numbers(self, holder, institution):
        assert profile_for_national_id(NATIONAL_ID) is None
        attest_citizenship(profile=holder, national_id=NATIONAL_ID, organization=institution)
        assert profile_for_national_id(NATIONAL_ID).pk == holder.pk

    def test_lookup_tolerates_malformed_input(self, db):
        assert profile_for_national_id("not-a-number") is None


@pytest.mark.django_db
class TestDatabaseInvariants:
    """
    Enforced in the database, not only in the service layer. Management
    commands, the admin, fixtures and future code paths all write these tables;
    a rule living in one function holds only until someone adds a second writer.
    """

    def test_attested_number_is_unique(self, holder, institution):
        attest_citizenship(profile=holder, national_id=NATIONAL_ID, organization=institution)
        other, _ = get_or_create_account(email="second@example.com")
        with pytest.raises(IntegrityError), transaction.atomic():
            SeekerProfile.objects.filter(pk=other.pk).update(
                national_id_hmac=idc.national_id_hmac(NATIONAL_ID)
            )

    def test_many_accounts_may_have_no_citizenship_number(self):
        get_or_create_account(email="a@example.com")
        get_or_create_account(email="b@example.com")
        assert SeekerProfile.objects.filter(national_id_hmac="").count() >= 2

    def test_citizenship_level_without_a_number_is_rejected(self, holder):
        """
        The level is what a verifier is told they may rely on. Claiming it
        without a number would make the subject-match guarantee a lie.
        """
        with pytest.raises(IntegrityError), transaction.atomic():
            SeekerProfile.objects.filter(pk=holder.pk).update(
                identity_level=IdentityLevel.CITIZENSHIP
            )
