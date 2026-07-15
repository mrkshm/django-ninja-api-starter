from django.contrib.auth import get_user_model
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from organizations.models import Organization

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
