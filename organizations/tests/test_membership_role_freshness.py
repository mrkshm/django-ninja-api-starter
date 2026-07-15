import pytest
from django.contrib.auth import get_user_model

from organizations.access import get_membership_role, is_org_admin, is_org_member
from organizations.models import Membership, Organization

User = get_user_model()


@pytest.mark.django_db
def test_queryset_update_is_reflected_immediately():
    user = User.objects.create_user(email="role-update@example.com", password="pw")
    organization = Organization.objects.create(
        name="Role update", slug="role-update", type="group"
    )
    Membership.objects.create(user=user, organization=organization, role="owner")
    assert is_org_admin(user, organization) is True

    Membership.objects.filter(user=user, organization=organization).update(
        role="member"
    )

    assert get_membership_role(user, organization) == "member"
    assert is_org_admin(user, organization) is False


@pytest.mark.django_db
def test_bulk_update_is_reflected_immediately():
    user = User.objects.create_user(email="role-bulk-update@example.com", password="pw")
    organization = Organization.objects.create(
        name="Role bulk update", slug="role-bulk-update", type="group"
    )
    membership = Membership.objects.create(
        user=user, organization=organization, role="owner"
    )
    assert is_org_admin(user, organization) is True

    membership.role = "member"
    Membership.objects.bulk_update([membership], ["role"])

    assert get_membership_role(user, organization) == "member"
    assert is_org_admin(user, organization) is False


@pytest.mark.django_db
def test_bulk_create_is_reflected_immediately():
    user = User.objects.create_user(email="role-bulk-create@example.com", password="pw")
    organization = Organization.objects.create(
        name="Role bulk create", slug="role-bulk-create", type="group"
    )
    assert is_org_member(user, organization) is False

    Membership.objects.bulk_create(
        [Membership(user=user, organization=organization, role="member")]
    )

    assert get_membership_role(user, organization) == "member"
    assert is_org_member(user, organization) is True
