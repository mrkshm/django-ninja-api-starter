from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from ninja.errors import HttpError

from contacts.models import Contact
from organizations.access import (
    assert_org_admin,
    assert_org_scoped_object_write,
    assert_org_view,
    assert_org_write,
    get_membership_role,
    is_org_admin,
    is_org_member,
    is_org_owner,
    is_platform_admin,
    visible_org_scoped_queryset,
)
from organizations.models import Membership, Organization


@pytest.mark.django_db
def test_platform_admin_is_explicit_staff_or_superuser():
    User = get_user_model()
    regular = User.objects.create_user(email="access-regular@example.com", password="pw")
    staff = User.objects.create_user(email="access-staff@example.com", password="pw", is_staff=True)
    superuser = User.objects.create_superuser(email="access-super@example.com", password="pw")

    assert is_platform_admin(regular) is False
    assert is_platform_admin(staff) is True
    assert is_platform_admin(superuser) is True


@pytest.mark.django_db
def test_membership_role_drives_org_permissions():
    User = get_user_model()
    owner = User.objects.create_user(email="access-owner@example.com", password="pw")
    admin = User.objects.create_user(email="access-admin@example.com", password="pw")
    member = User.objects.create_user(email="access-member@example.com", password="pw")
    outsider = User.objects.create_user(email="access-outsider@example.com", password="pw")
    org = Organization.objects.create(name="Access", slug="access", type="group")
    Membership.objects.create(user=owner, organization=org, role="owner")
    Membership.objects.create(user=admin, organization=org, role="admin")
    Membership.objects.create(user=member, organization=org, role="member")

    assert get_membership_role(owner, org) == "owner"
    assert is_org_owner(owner, org) is True
    assert is_org_admin(owner, org) is True
    assert is_org_admin(admin, org) is True
    assert is_org_member(member, org) is True
    assert get_membership_role(outsider, org) is None
    assert is_org_member(outsider, org) is False


@pytest.mark.django_db
def test_org_assertions_raise_403_for_insufficient_role():
    User = get_user_model()
    member = User.objects.create_user(email="access-member-assert@example.com", password="pw")
    outsider = User.objects.create_user(email="access-outsider-assert@example.com", password="pw")
    org = Organization.objects.create(name="Assert", slug="assert", type="group")
    Membership.objects.create(user=member, organization=org, role="member")

    assert assert_org_view(member, org) is None
    assert assert_org_write(member, org) is None

    with pytest.raises(HttpError) as view_exc:
        assert_org_view(outsider, org)
    assert view_exc.value.status_code == 403

    with pytest.raises(HttpError) as admin_exc:
        assert_org_admin(member, org)
    assert admin_exc.value.status_code == 403


@pytest.mark.django_db
def test_org_scoped_object_write_handles_global_objects():
    User = get_user_model()
    regular = User.objects.create_user(email="access-global-regular@example.com", password="pw")
    staff = User.objects.create_user(email="access-global-staff@example.com", password="pw", is_staff=True)
    global_obj = SimpleNamespace(organization=None, organization_id=None)

    with pytest.raises(HttpError):
        assert_org_scoped_object_write(regular, global_obj)

    assert assert_org_scoped_object_write(staff, global_obj) is None


@pytest.mark.django_db
def test_visible_org_scoped_queryset_filters_memberships():
    User = get_user_model()
    user = User.objects.create_user(email="access-visible@example.com", password="pw")
    first = Organization.objects.create(name="FirstVisible", slug="first-visible", type="group")
    second = Organization.objects.create(name="SecondVisible", slug="second-visible", type="group")
    Membership.objects.create(user=user, organization=first, role="member")
    visible = Contact.objects.create(display_name="Visible", slug="visible", organization=first, creator=user)
    Contact.objects.create(display_name="Hidden", slug="hidden", organization=second, creator=user)

    qs = visible_org_scoped_queryset(user, Contact.objects.all())

    assert list(qs) == [visible]
