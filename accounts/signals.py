from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.core.cache import cache
from django.contrib.auth import get_user_model

User = get_user_model()

@receiver(m2m_changed, sender=User.user_permissions.through)
def invalidate_user_permissions_cache(sender, instance, action, **kwargs):
    if action in ("post_add", "post_remove", "post_clear"):
        cache_key = f"user_permissions_{instance.id}"
        cache.delete(cache_key)

# If you use groups, also listen for group membership changes:
from django.contrib.auth.models import Group

@receiver(m2m_changed, sender=User.groups.through)
def invalidate_user_group_permissions_cache(sender, instance, action, **kwargs):
    if action in ("post_add", "post_remove", "post_clear"):
        cache_key = f"user_permissions_{instance.id}"
        cache.delete(cache_key)
