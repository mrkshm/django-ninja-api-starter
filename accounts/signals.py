from django.db.models.signals import post_delete
from django.dispatch import receiver

from accounts.models import User
from core.utils.avatar import schedule_avatar_file_deletion


@receiver(post_delete, sender=User, dispatch_uid="accounts.delete_user_avatar")
def delete_user_avatar_after_commit(sender, instance, **kwargs):
    schedule_avatar_file_deletion(instance.avatar_path)
