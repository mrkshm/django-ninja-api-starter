import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from ninja.errors import HttpError

from organizations.access import (
    NO_MEMBERSHIP_ROLE,
    assert_org_scoped_object_write,
    get_membership_role,
    is_org_admin,
    is_org_member,
    is_org_owner,
    is_platform_admin,
    member_org_ids,
    membership_role_cache_key,
)
from organizations.models import Membership, Organization


@pytest.mark.django_db
def test_owner_role_implies_admin_and_member():
    User = get_user_model()
    user = User.objects.create_user(email="owner@example.com", password="pass")
    org = Organization.objects.create(name="OwnerOrg", slug="owner-org", type="personal", creator=user)
    Membership.objects.create(user=user, organization=org, role="owner")

    assert get_membership_role(user, org) == "owner"
    assert is_org_owner(user, org) is True
    assert is_org_admin(user, org) is True
    assert is_org_member(user, org) is True


@pytest.mark.django_db
def test_platform_admin_uses_django_staff_or_superuser_flags():
    User = get_user_model()
    regular = User.objects.create_user(email="regular@example.com", password="pass")
    staff = User.objects.create_user(email="staff@example.com", password="pass", is_staff=True)
    superuser = User.objects.create_superuser(email="super@example.com", password="pass")

    assert is_platform_admin(regular) is False
    assert is_platform_admin(staff) is True
    assert is_platform_admin(superuser) is True


@pytest.mark.django_db
def test_member_org_ids_returns_user_membership_org_ids():
    User = get_user_model()
    user = User.objects.create_user(email="member-orgs@example.com", password="pass")
    first = Organization.objects.create(name="First", slug="first", type="group")
    second = Organization.objects.create(name="Second", slug="second", type="group")
    Membership.objects.create(user=user, organization=first, role="member")
    Membership.objects.create(user=user, organization=second, role="owner")

    assert {first.id, second.id} <= set(member_org_ids(user))


@pytest.mark.django_db
def test_org_scoped_object_write_allows_platform_admin_and_member():
    User = get_user_model()
    member = User.objects.create_user(email="writer@example.com", password="pass")
    staff = User.objects.create_user(email="staff-writer@example.com", password="pass", is_staff=True)
    org = Organization.objects.create(name="Writable", slug="writable", type="group")
    Membership.objects.create(user=member, organization=org, role="member")
    obj = type("OrgObject", (), {"organization": org, "organization_id": org.id})()

    assert assert_org_scoped_object_write(member, obj) is None
    assert assert_org_scoped_object_write(staff, obj) is None


@pytest.mark.django_db
def test_org_scoped_object_write_rejects_non_member():
    User = get_user_model()
    user = User.objects.create_user(email="outsider@example.com", password="pass")
    org = Organization.objects.create(name="Private", slug="private", type="group")
    obj = type("OrgObject", (), {"organization": org, "organization_id": org.id})()

    with pytest.raises(HttpError):
        assert_org_scoped_object_write(user, obj)


@pytest.mark.django_db
def test_org_scoped_object_write_rejects_global_object_for_regular_user():
    User = get_user_model()
    user = User.objects.create_user(email="global-outsider@example.com", password="pass")
    obj = type("GlobalObject", (), {"organization": None, "organization_id": None})()

    with pytest.raises(HttpError) as exc_info:
        assert_org_scoped_object_write(user, obj, global_message="Admins only.")

    assert exc_info.value.status_code == 403
    assert exc_info.value.message == "Admins only."


@pytest.mark.django_db
def test_org_admin_role():
    User = get_user_model()
    user = User.objects.create_user(email="admin@example.com", password="pass")
    org = Organization.objects.create(name="GroupOrg", slug="group-org", type="group", creator=None)
    Membership.objects.create(user=user, organization=org, role="admin")

    assert is_org_owner(user, org) is False
    assert is_org_admin(user, org) is True
    assert is_org_member(user, org) is True


@pytest.mark.django_db
def test_org_member_role():
    User = get_user_model()
    user = User.objects.create_user(email="member@example.com", password="pass")
    org = Organization.objects.create(name="GroupOrg2", slug="group-org2", type="group", creator=None)
    Membership.objects.create(user=user, organization=org, role="member")

    assert is_org_owner(user, org) is False
    assert is_org_admin(user, org) is False
    assert is_org_member(user, org) is True


@pytest.mark.django_db
def test_non_member_role():
    User = get_user_model()
    user = User.objects.create_user(email="notamember@example.com", password="pass")
    org = Organization.objects.create(name="OtherOrg", slug="other-org", type="group", creator=None)

    assert get_membership_role(user, org) is None
    assert is_org_owner(user, org) is False
    assert is_org_admin(user, org) is False
    assert is_org_member(user, org) is False


@pytest.mark.django_db
def test_membership_role_caches_result():
    User = get_user_model()
    user = User.objects.create_user(email="member@example.com", password="pass")
    org = Organization.objects.create(name="CacheOrg", slug="cache-org", type="group", creator=None)
    Membership.objects.create(user=user, organization=org, role="member")
    cache_key = membership_role_cache_key(user.id, org.id)

    cache.delete(cache_key)
    assert is_org_member(user, org) is True
    assert cache.get(cache_key) == "member"

    Membership.objects.filter(user=user, organization=org).delete()
    assert is_org_member(user, org) is False
    assert cache.get(cache_key) == NO_MEMBERSHIP_ROLE


@pytest.mark.django_db
def test_membership_role_cache_invalidation():
    User = get_user_model()
    user = User.objects.create_user(email="invalidate@example.com", password="pass")
    org = Organization.objects.create(name="InvalidateOrg", slug="invalidate-org", type="group", creator=None)
    Membership.objects.create(user=user, organization=org, role="member")
    cache_key = membership_role_cache_key(user.id, org.id)

    assert is_org_member(user, org) is True
    assert cache.get(cache_key) == "member"

    Membership.objects.filter(user=user, organization=org).delete()
    assert is_org_member(user, org) is False
    assert cache.get(cache_key) == NO_MEMBERSHIP_ROLE


@pytest.mark.django_db
def test_membership_role_cache_invalidation_on_add():
    User = get_user_model()
    user = User.objects.create_user(email="addinvalidate@example.com", password="pass")
    org = Organization.objects.create(name="AddInvalidateOrg", slug="add-invalidate-org", type="group", creator=None)
    cache_key = membership_role_cache_key(user.id, org.id)

    cache.delete(cache_key)
    assert is_org_member(user, org) is False
    assert cache.get(cache_key) == NO_MEMBERSHIP_ROLE

    Membership.objects.create(user=user, organization=org, role="member")
    assert is_org_member(user, org) is True
    assert cache.get(cache_key) == "member"
