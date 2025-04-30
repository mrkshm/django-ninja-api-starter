from celery import shared_task
from images.models import Image
import os
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

@shared_task
def cleanup_orphaned_images():
    # Find all images with no relations
    orphaned = Image.objects.filter(relations__isnull=True)
    deleted_count = 0
    for image in orphaned:
        # Delete main file
        file_path = image.file.path
        if os.path.exists(file_path):
            os.remove(file_path)
        # Delete variants
        base, ext = os.path.splitext(file_path)
        for suffix in ["_thumb", "_sm", "_md", "_lg"]:
            variant_path = f"{base}{suffix}.webp"
            if os.path.exists(variant_path):
                os.remove(variant_path)
        image.delete()
        deleted_count += 1
    logger.info(f"Deleted {deleted_count} orphaned images and their variants.")

@shared_task
def cleanup_orphaned_images_task():
    return cleanup_orphaned_images()
