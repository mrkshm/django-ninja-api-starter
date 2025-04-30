from django.db import transaction
from tags.models import Tag
from celery import shared_task

def cleanup_orphaned_tags():
    """
    Delete tags that are not referenced by any TaggedItem.
    Returns the number of tags deleted.
    """
    with transaction.atomic():
        orphaned_tags = Tag.objects.filter(taggeditem__isnull=True)
        count = orphaned_tags.count()
        orphaned_tags.delete()
        return count

@shared_task
def cleanup_orphaned_tags_task():
    return cleanup_orphaned_tags()
