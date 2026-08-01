"""
The organisation directory: a picker, not a scrape.

Added because the seeker-claim flow needs a way to name an employer by id, and
no endpoint a citizen could read exposed one. The point of these tests is the
boundary that keeps it from becoming something else: approved organisations
only, names only, and never anonymously.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.organizations.models import Organization, OrganizationKind, OrganizationStatus


@pytest.fixture
def citizen_client(db, holder):
    client = APIClient()
    client.force_authenticate(user=holder.user)
    return client


@pytest.fixture
def pending_org(db):
    return Organization.objects.create(
        kind=OrganizationKind.EMPLOYER,
        legal_name="Not Yet Approved Ltd",
        slug="not-yet-approved",
        registration_number="PAN-PENDING",
        contact_email="hr@pending.example",
        status=OrganizationStatus.PENDING,
    )


def rows(response):
    return response.data["results"] if "results" in response.data else response.data


@pytest.mark.django_db
class TestDirectory:
    def test_a_citizen_can_list_approved_organisations(self, citizen_client, institution, employer):
        response = citizen_client.get("/api/v1/organizations/directory/")
        assert response.status_code == 200

        names = {row["legal_name"] for row in rows(response)}
        assert names == {"Tribhuvan University", "Leapfrog Technology"}

    def test_it_can_be_narrowed_to_employers(self, citizen_client, institution, employer):
        response = citizen_client.get("/api/v1/organizations/directory/?kind=EMPLOYER")
        assert [row["legal_name"] for row in rows(response)] == ["Leapfrog Technology"]

    def test_an_unapproved_organisation_is_not_listed(self, citizen_client, pending_org):
        """
        Claiming a job at an organisation that cannot log in is claiming
        something nobody is able to dispute.
        """
        response = citizen_client.get("/api/v1/organizations/directory/")
        assert rows(response) == []

    def test_it_exposes_a_name_and_nothing_else(self, citizen_client, employer):
        row = rows(citizen_client.get("/api/v1/organizations/directory/"))[0]
        assert set(row) == {"id", "legal_name", "kind", "slug"}
        # Contact details, address, registration number and chain address are
        # all absent by construction — this is a picker, not a business
        # directory to harvest.
        for leaked in ("contact_email", "contact_phone", "address", "chain_address"):
            assert leaked not in row

    def test_anonymous_callers_get_nothing(self, db, employer):
        assert APIClient().get("/api/v1/organizations/directory/").status_code == 401


@pytest.mark.django_db
class TestClaimUsesTheDirectory:
    def test_an_id_from_the_directory_is_accepted_by_the_claim_endpoint(
        self, citizen_client, employer
    ):
        listing = rows(citizen_client.get("/api/v1/organizations/directory/?kind=EMPLOYER"))
        response = citizen_client.post(
            "/api/v1/credentials/claim-experience/",
            {
                "employer": listing[0]["id"],
                "detail": {
                    "job_title": "Software Engineer",
                    "employment_type": "FULL_TIME",
                    "start_date": "2022-01-01",
                    "end_date": "2023-06-30",
                    "departure_status": "RESIGNED",
                },
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["status"] == "PENDING_REVIEW"

    def test_an_institution_cannot_be_claimed_against_as_an_employer(
        self, citizen_client, institution
    ):
        response = citizen_client.post(
            "/api/v1/credentials/claim-experience/",
            {
                "employer": str(institution.pk),
                "detail": {
                    "job_title": "Lecturer",
                    "employment_type": "FULL_TIME",
                    "start_date": "2022-01-01",
                    "end_date": "2023-06-30",
                    "departure_status": "RESIGNED",
                },
            },
            format="json",
        )
        assert response.status_code == 400

    def test_a_registrar_account_cannot_file_a_claim(self, db, employer):
        registrar = User.objects.create_user(
            email="registrar@aafnopraman.np",
            password="a-very-long-registrar-password",
            full_name="Platform Registrar",
            role=Role.REGISTRAR,
        )
        client = APIClient()
        client.force_authenticate(user=registrar)

        response = client.post(
            "/api/v1/credentials/claim-experience/",
            {"employer": str(employer.pk), "detail": {}},
            format="json",
        )
        assert response.status_code == 403
