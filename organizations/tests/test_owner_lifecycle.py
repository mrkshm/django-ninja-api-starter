import pytest
from django.contrib.auth import get_user_model

from accounts.services import set_user_active_status
from organizations.models import Membership, Organization
from organizations.services import (
    ActiveOwnerRequiredError,
    change_membership_role,
    create_group_organization,
    remove_membership,
)

User = get_user_model()


@pytest.mark.django_db
def test_group_creation_assigns_initial_owner_atomically():
    owner = User.objects.create_user(email="initial-owner@example.com", password="pw")

    organization = create_group_organization(
        name="New group",
        slug="new-group",
        owner=owner,
    )

    assert Membership.objects.filter(
        organization=organization, user=owner, role="owner"
    ).exists()


@pytest.fixture
def group_with_owner():
    owner = User.objects.create_user(email="owner-lifecycle@example.com", password="pw")
    organization = Organization.objects.create(
        name="Owner lifecycle", slug="owner-lifecycle", type="group"
    )
    membership = Membership.objects.create(
        user=owner, organization=organization, role="owner"
    )
    return organization, owner, membership


@pytest.mark.django_db
def test_last_active_owner_cannot_be_demoted(group_with_owner):
    _organization, _owner, membership = group_with_owner

    with pytest.raises(ActiveOwnerRequiredError):
        change_membership_role(membership, role="admin")

    membership.refresh_from_db()
    assert membership.role == "owner"


@pytest.mark.django_db
def test_last_active_owner_cannot_be_removed(group_with_owner):
    _organization, _owner, membership = group_with_owner

    with pytest.raises(ActiveOwnerRequiredError):
        remove_membership(membership)

    assert Membership.objects.filter(pk=membership.pk).exists()


@pytest.mark.django_db
def test_owner_can_leave_after_promoting_an_active_successor(group_with_owner):
    organization, _owner, membership = group_with_owner
    successor = User.objects.create_user(
        email="owner-successor@example.com", password="pw"
    )
    successor_membership = Membership.objects.create(
        user=successor, organization=organization, role="member"
    )

    change_membership_role(successor_membership, role="owner")
    remove_membership(membership)

    assert Membership.objects.filter(
        organization=organization, user=successor, role="owner"
    ).exists()


@pytest.mark.django_db
def test_last_active_owner_cannot_be_deactivated(group_with_owner):
    _organization, owner, _membership = group_with_owner

    with pytest.raises(ActiveOwnerRequiredError):
        set_user_active_status(owner, is_active=False)

    owner.refresh_from_db()
    assert owner.is_active is True


@pytest.mark.django_db
def test_owner_can_be_deactivated_when_an_active_owner_remains(group_with_owner):
    organization, owner, _membership = group_with_owner
    successor = User.objects.create_user(
        email="active-owner-successor@example.com", password="pw"
    )
    Membership.objects.create(user=successor, organization=organization, role="owner")

    set_user_active_status(owner, is_active=False)

    owner.refresh_from_db()
    assert owner.is_active is False
