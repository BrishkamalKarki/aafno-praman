"""
Registrar-driven provisioning: the platform has no self-service signup for
organisations, so the registrar creates every account and hands over a password.

The property worth protecting here is atomicity. An organisation created in the
database but absent from the contract cannot issue, and its staff have no way to
tell why — so a ledger failure must leave nothing behind at all.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.organizations.models import Organization, OrganizationStatus


@pytest.fixture
def registrar(db):
    return User.objects.create_user(
        email="registrar@aafnopraman.np",
        password="a-very-long-registrar-password",
        full_name="Platform Registrar",
        role=Role.REGISTRAR,
    )


@pytest.fixture
def registrar_client(registrar):
    client = APIClient()
    client.force_authenticate(user=registrar)
    return client


@pytest.fixture
def seeker_client(db):
    user = User.objects.create_user(
        email="citizen@example.com",
        password="a-perfectly-ordinary-password",
        full_name="A Citizen",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestProvisionSeeker:
    def test_creates_a_citizen_with_a_usable_password(self, registrar_client):
        response = registrar_client.post(
            "/api/v1/registrar/provision/user/",
            {
                "full_name": "Sita Sharma",
                "email": "Sita.New@Example.com",
                "phone": "9800000000",
                "date_of_birth": "2000-01-15",
            },
            format="json",
        )
        assert response.status_code == 201, response.data

        user = User.objects.get(email="sita.new@example.com")
        assert user.role == Role.SEEKER
        # The generated password is returned once and must actually work — a
        # response that showed a password the account does not have would be
        # discovered only by the person locked out of it.
        assert user.check_password(response.data["temp_password"])
        assert user.seeker_profile.date_of_birth.isoformat() == "2000-01-15"

    def test_citizenship_number_is_never_taken_from_this_form(self, registrar_client):
        """Only an approved issuer may attest one — see SeekerProfile's docstring."""
        response = registrar_client.post(
            "/api/v1/registrar/provision/user/",
            {
                "full_name": "Someone",
                "email": "someone@example.com",
                "citizenship_number": "12-01-70-98765",
            },
            format="json",
        )
        assert response.status_code == 201
        profile = User.objects.get(email="someone@example.com").seeker_profile
        assert profile.national_id_hmac == ""
        assert profile.identity_level == "EMAIL_ONLY"

    def test_duplicate_email_is_rejected(self, registrar_client, holder):
        response = registrar_client.post(
            "/api/v1/registrar/provision/user/",
            {"full_name": "Dupe", "email": holder.user.email},
            format="json",
        )
        assert response.status_code == 400

    def test_a_citizen_cannot_provision_accounts(self, seeker_client):
        response = seeker_client.post(
            "/api/v1/registrar/provision/user/",
            {"full_name": "Nope", "email": "nope@example.com"},
            format="json",
        )
        assert response.status_code == 403

    def test_anonymous_cannot_provision_accounts(self, db):
        response = APIClient().post(
            "/api/v1/registrar/provision/user/",
            {"full_name": "Nope", "email": "nope2@example.com"},
            format="json",
        )
        assert response.status_code == 401


@pytest.mark.django_db
class TestProvisionOrganization:
    def test_creates_and_approves_an_institution_on_chain(self, registrar_client, stub_ledger):
        response = registrar_client.post(
            "/api/v1/registrar/provision/organization/",
            {
                "kind": "INSTITUTION",
                "legal_name": "Kathmandu University",
                "email": "registrar@ku.edu.np",
                "registration_number": "UGC-9001",
                "contact_person": "Ramesh KC",
                "phone": "01-5000000",
                "address": "Dhulikhel, Nepal",
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["organization"]["status"] == OrganizationStatus.APPROVED
        assert response.data["organization"]["can_issue"] is True

        organization = Organization.objects.get(registration_number="UGC-9001")
        assert organization.chain_address
        owner = User.objects.get(email="registrar@ku.edu.np")
        assert owner.role == Role.ORG_MEMBER
        assert owner.check_password(response.data["temp_password"])
        assert organization.memberships.filter(user=owner, role="OWNER").exists()

    def test_creates_an_employer(self, registrar_client, stub_ledger):
        response = registrar_client.post(
            "/api/v1/registrar/provision/organization/",
            {
                "kind": "EMPLOYER",
                "legal_name": "Acme Nepal",
                "email": "hr@acme.com.np",
                "registration_number": "PAN-77001",
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["organization"]["kind"] == "EMPLOYER"

    def test_a_ledger_failure_leaves_nothing_behind(self, registrar_client):
        """
        No ``stub_ledger`` here, so the chain is genuinely disabled and approval
        genuinely fails. Nothing — organisation, user, membership — may survive.
        """
        response = registrar_client.post(
            "/api/v1/registrar/provision/organization/",
            {
                "kind": "EMPLOYER",
                "legal_name": "Doomed Co",
                "email": "doomed@example.com",
                "registration_number": "PAN-00000",
            },
            format="json",
        )
        assert response.status_code >= 400
        assert not Organization.objects.filter(registration_number="PAN-00000").exists()
        assert not User.objects.filter(email="doomed@example.com").exists()

    def test_duplicate_registration_number_is_rejected(self, registrar_client, institution):
        response = registrar_client.post(
            "/api/v1/registrar/provision/organization/",
            {
                "kind": institution.kind,
                "legal_name": "Another Name Entirely",
                "email": "another@example.com",
                "registration_number": institution.registration_number,
            },
            format="json",
        )
        assert response.status_code == 400

    def test_a_citizen_cannot_provision_an_organisation(self, seeker_client):
        response = seeker_client.post(
            "/api/v1/registrar/provision/organization/",
            {
                "kind": "EMPLOYER",
                "legal_name": "Nope Inc",
                "email": "nope3@example.com",
                "registration_number": "PAN-1",
            },
            format="json",
        )
        assert response.status_code == 403
