"""
The free allowance is one number, defined in three places.

`FREE_PLAN_MONTHLY_LOOKUPS` in settings is what provisioning writes onto a new
subscription; `Subscription.monthly_lookup_limit`'s column default is what a row
created without going through provisioning gets; and `PLANS.COMMUNITY` in the
frontend is the figure printed on the pricing page and the quota meter.

They have drifted before — settings said 15, the column said 50, and the UI
advertised 10, so an employer was told they had ten checks, actually had fifty,
and got a different answer again depending on how their account was created.
None of it errored, which is exactly why it survived: a wrong allowance looks
like a working allowance right up until someone counts.

These tests pin the two the backend owns. The frontend constant carries a
comment pointing here; nothing but review keeps that one honest, because a
TypeScript literal is not reachable from pytest.
"""

import pytest
from django.conf import settings

from apps.organizations.models import Organization, OrganizationKind, OrganizationStatus, Plan, Subscription


@pytest.mark.django_db
class TestFreeAllowanceIsOneNumber:
    def test_the_setting_and_the_column_default_agree(self):
        """
        The column default only applies to rows created outside provisioning —
        a fixture, a data migration, the Django admin. Disagreeing with the
        setting means those accounts silently meter differently from every
        account the API created.
        """
        column_default = Subscription._meta.get_field("monthly_lookup_limit").default
        assert column_default == settings.FREE_PLAN_MONTHLY_LOOKUPS

    def test_the_advertised_free_allowance_is_fifty(self):
        """
        Pinned as a literal on purpose. The two assertions above only prove the
        definitions agree with each other; they would pass just as happily if
        both were wrong. This is the one that fails when someone changes the
        number without changing the pricing page.
        """
        assert settings.FREE_PLAN_MONTHLY_LOOKUPS == 50

    def test_a_subscription_created_directly_gets_the_free_allowance(self):
        # PENDING, not APPROVED: `org_approved_requires_chain_address` refuses
        # an approved organisation with no custodial address, which is the
        # database refusing to let an issuer exist that the contract would
        # reject. The subscription default is what is under test here, and it
        # does not depend on approval.
        organization = Organization.objects.create(
            kind=OrganizationKind.EMPLOYER,
            legal_name="Direct Insert Ltd",
            slug="direct-insert",
            registration_number="PAN-DIRECT",
            contact_email="hr@direct.example",
            status=OrganizationStatus.PENDING,
        )
        subscription = Subscription.objects.create(organization=organization)

        assert subscription.plan == Plan.FREE
        assert subscription.monthly_lookup_limit == settings.FREE_PLAN_MONTHLY_LOOKUPS
        assert subscription.is_unlimited is False
