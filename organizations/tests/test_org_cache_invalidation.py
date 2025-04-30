import pytest
from django.contrib.auth import get_user_model
from organizations.models import Organization, Membership
from organizations.permissions import is_owner, is_admin, is_member
from django.core.cache import cache

User = get_user_model()

@pytest.mark.django_db
def test_membership_cache_invalidation():
    user = User.objects.create_user(email="test@example.com", password="pw")
    org = Organization.objects.create(name="TestOrg", slug="test-org", type="group")
    # Membership does not exist yet
    assert not is_member(user, org)
    assert cache.get(f'is_member_{user.id}_{org.id}') is not None
    # Add membership
    m = Membership.objects.create(user=user, organization=org, role="member")
    # Cache should be invalidated, so next call should repopulate
    cache.set(f'is_member_{user.id}_{org.id}', False)
    m.role = "admin"
    m.save()  # Should invalidate all relevant keys
    assert cache.get(f'is_member_{user.id}_{org.id}') is None
    assert cache.get(f'is_admin_{user.id}_{org.id}') is None
    assert cache.get(f'is_owner_{user.id}_{org.id}') is None
    # Remove membership
    m.delete()
    assert cache.get(f'is_member_{user.id}_{org.id}') is None
    assert cache.get(f'is_admin_{user.id}_{org.id}') is None
    assert cache.get(f'is_owner_{user.id}_{org.id}') is None
