import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from organizations.models import Organization, Membership
from organizations.permissions import is_admin, is_owner, is_member

@pytest.mark.django_db
def test_is_owner_for_personal_org():
    User = get_user_model()
    user = User.objects.create_user(email="owner@example.com", password="pass")
    org = Organization.objects.create(name="OwnerOrg", slug="owner-org", type="personal", creator=user)
    Membership.objects.create(user=user, organization=org, role="owner")
    assert is_owner(user, org) is True
    assert is_admin(user, org) is True
    assert is_member(user, org) is True

@pytest.mark.django_db
def test_is_admin_for_group_org():
    User = get_user_model()
    user = User.objects.create_user(email="admin@example.com", password="pass")
    org = Organization.objects.create(name="GroupOrg", slug="group-org", type="group", creator=None)
    Membership.objects.create(user=user, organization=org, role="admin")
    assert is_owner(user, org) is False
    assert is_admin(user, org) is True
    assert is_member(user, org) is True

@pytest.mark.django_db
def test_is_member_for_group_org():
    User = get_user_model()
    user = User.objects.create_user(email="member@example.com", password="pass")
    org = Organization.objects.create(name="GroupOrg2", slug="group-org2", type="group", creator=None)
    Membership.objects.create(user=user, organization=org, role="member")
    assert is_owner(user, org) is False
    assert is_admin(user, org) is False
    assert is_member(user, org) is True

@pytest.mark.django_db
def test_not_a_member():
    User = get_user_model()
    user = User.objects.create_user(email="notamember@example.com", password="pass")
    org = Organization.objects.create(name="OtherOrg", slug="other-org", type="group", creator=None)
    assert is_owner(user, org) is False
    assert is_admin(user, org) is False
    assert is_member(user, org) is False

@pytest.mark.django_db
def test_is_member_caches_result():
    User = get_user_model()
    user = User.objects.create_user(email="member@example.com", password="pass")
    org = Organization.objects.create(name="CacheOrg", slug="cache-org", type="group", creator=None)
    Membership.objects.create(user=user, organization=org, role="member")
    cache_key = f'is_member_{user.id}_{org.id}'
    # Ensure cache is empty
    cache.delete(cache_key)
    # First call should populate the cache
    assert is_member(user, org) is True
    # Now the cache should have the value
    cached = cache.get(cache_key)
    assert cached is True
    # Remove membership and invalidate cache
    Membership.objects.filter(user=user, organization=org).delete()
    # Simulate what your signal does (in case signals are not triggered synchronously in test)
    cache.delete(cache_key)
    # Now the cache should be empty again
    assert cache.get(cache_key) is None
    # Next call should return False and repopulate cache
    assert is_member(user, org) is False
    assert cache.get(cache_key) is False

@pytest.mark.django_db
def test_is_member_cache_invalidation():
    User = get_user_model()
    user = User.objects.create_user(email="invalidate@example.com", password="pass")
    org = Organization.objects.create(name="InvalidateOrg", slug="invalidate-org", type="group", creator=None)
    Membership.objects.create(user=user, organization=org, role="member")
    cache_key = f'is_member_{user.id}_{org.id}'
    # Prime the cache
    assert is_member(user, org) is True
    assert cache.get(cache_key) is True
    # Remove membership, which should trigger invalidation via signal
    Membership.objects.filter(user=user, organization=org).delete()
    # After deletion, cache should be invalidated (may need to force signal processing)
    # Call is_member again, should be False and cache updated
    assert is_member(user, org) is False
    assert cache.get(cache_key) is False

@pytest.mark.django_db
def test_is_member_cache_invalidation_on_add():
    User = get_user_model()
    user = User.objects.create_user(email="addinvalidate@example.com", password="pass")
    org = Organization.objects.create(name="AddInvalidateOrg", slug="add-invalidate-org", type="group", creator=None)
    cache_key = f'is_member_{user.id}_{org.id}'
    # Prime cache as False (user is not a member)
    cache.delete(cache_key)
    assert is_member(user, org) is False
    assert cache.get(cache_key) is False
    # Add membership, which should trigger invalidation via signal
    Membership.objects.create(user=user, organization=org, role="member")
    # Call is_member again, should be True and cache updated
    assert is_member(user, org) is True
    assert cache.get(cache_key) is True
