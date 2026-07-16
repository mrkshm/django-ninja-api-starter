from django.db.models.signals import post_delete
from django.dispatch import receiver

from contacts.models import Contact
from core.utils.avatar import schedule_avatar_file_deletion


@receiver(post_delete, sender=Contact, dispatch_uid="contacts.delete_contact_avatar")
def delete_contact_avatar_after_commit(sender, instance, **kwargs):
    schedule_avatar_file_deletion(instance.avatar_path)
