import pytest
from django.contrib.auth import get_user_model

from organizations.models import Membership
from organizations.tests.utils import create_test_group


@pytest.mark.django_db
def test_membership_string_does_not_fetch_related_rows(django_assert_num_queries):
    user = get_user_model().objects.create_user(
        email="membership-display@example.com",
        password="pw",
    )
    organization = create_test_group(name="Display org", slug="display-org")
    membership = Membership.objects.create(
        user=user,
        organization=organization,
        role="member",
    )
    unloaded = Membership.objects.only("id", "user_id", "organization_id", "role").get(
        pk=membership.pk
    )

    with django_assert_num_queries(0):
        label = str(unloaded)

    assert f"user={user.pk}" in label
    assert f"organization={organization.pk}" in label
