import pytest
from django.contrib.auth import get_user_model
from organizations.access import (
    is_org_admin,
    is_org_member,
    is_org_owner,
    membership_role_cache_key,
)
from organizations.models import Organization, Membership
from django.core.cache import cache

User = get_user_model()


@pytest.mark.django_db
def test_membership_cache_invalidation():
    user = User.objects.create_user(email="test@example.com", password="pw")
    org = Organization.objects.create(name="TestOrg", slug="test-org", type="group")
    role_cache_key = membership_role_cache_key(user.id, org.id)
    # Membership does not exist yet
    assert not is_org_member(user, org)
    assert cache.get(role_cache_key) is not None
    # Add membership
    m = Membership.objects.create(user=user, organization=org, role="member")
    # Cache should be invalidated, so next call should repopulate
    cache.set(role_cache_key, "member")
    m.role = "admin"
    m.save()  # Should invalidate all relevant keys
    assert cache.get(role_cache_key) is None
    assert is_org_admin(user, org) is True
    assert is_org_owner(user, org) is False
    # Remove membership
    m.delete()
    assert cache.get(role_cache_key) is None
