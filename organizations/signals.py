from django.db.models.signals import pre_delete, post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from organizations.models import Organization, Membership
from core.utils import make_it_unique
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

User = get_user_model()

@receiver(post_save, sender=User)
def create_personal_org_on_user_create(sender, instance, created, **kwargs):
    if created:
        if not Organization.objects.filter(type="personal", memberships__user=instance).exists():
            base_slug = instance.slug or f"user-{instance.pk}"
            slug = make_it_unique(base_slug, Organization, "slug")
            org = Organization.objects.create(
                name=instance.username or f"user-{instance.pk}",
                slug=slug,
                type="personal",
                creator=instance
            )
            Membership.objects.create(
                user=instance,
                organization=org,
                role="owner"
            )

@receiver(pre_delete, sender=User)
def delete_personal_org_on_user_delete(sender, instance, **kwargs):
    personal_orgs = Organization.objects.filter(
        type="personal",
        memberships__user=instance
    ).distinct()
    for org in personal_orgs:
        org.delete()

@receiver([post_save, post_delete], sender=Membership)
def invalidate_membership_cache(sender, instance, **kwargs):
    user_id = instance.user_id
    org_id = instance.organization_id
    for kind in ["is_owner", "is_admin", "is_member"]:
        cache_key = f"{kind}_{user_id}_{org_id}"
        cache.delete(cache_key)
