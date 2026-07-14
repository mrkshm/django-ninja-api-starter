from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from organizations.access import membership_role_cache_key
from organizations.models import Membership, Organization

User = get_user_model()


@receiver(pre_delete, sender=User)
def delete_personal_org_on_user_delete(sender, instance, **kwargs):
    # Only delete the account's own personal organization. Membership in another
    # user's personal organization must never make that organization a cascade target.
    personal_orgs = Organization.objects.filter(
        type="personal", creator=instance, memberships__user=instance
    ).distinct()
    for org in personal_orgs:
        org.delete()


@receiver([post_save, post_delete], sender=Membership)
def invalidate_membership_cache(sender, instance, **kwargs):
    user_id = instance.user_id
    org_id = instance.organization_id
    cache.delete(membership_role_cache_key(user_id, org_id))
    for kind in ["is_owner", "is_admin", "is_member"]:
        cache_key = f"{kind}_{user_id}_{org_id}"
        cache.delete(cache_key)
