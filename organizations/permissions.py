from organizations.models import Membership
from django.core.cache import cache

def is_owner(user, org):
    """Return True if user is an owner of the org."""
    cache_key = f'is_owner_{user.id}_{org.id}'
    result = cache.get(cache_key)
    if result is None:
        result = Membership.objects.filter(user=user, organization=org, role="owner").exists()
        cache.set(cache_key, result, timeout=3600)
    return result

def is_admin(user, org):
    """Return True if user is an admin or owner of the org (admin implies elevated rights)."""
    cache_key = f'is_admin_{user.id}_{org.id}'
    result = cache.get(cache_key)
    if result is None:
        result = Membership.objects.filter(user=user, organization=org, role__in=["admin", "owner"]).exists()
        cache.set(cache_key, result, timeout=3600)
    return result

def is_member(user, org):
    """Return True if user is a member (any role) of the org."""
    cache_key = f'is_member_{user.id}_{org.id}'
    result = cache.get(cache_key)
    if result is None:
        result = Membership.objects.filter(user=user, organization=org).exists()
        cache.set(cache_key, result, timeout=3600)
    return result