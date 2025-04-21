from django.db.models.signals import pre_delete, post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from organizations.models import Organization, Membership
from core.utils import make_it_unique

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
