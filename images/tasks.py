from celery import shared_task
from images.models import Image
import os
from django.core.files.storage import default_storage
import logging

logger = logging.getLogger(__name__)

@shared_task
def cleanup_orphaned_images():
    # Find all images with no relations
    orphaned = Image.objects.filter(relations__isnull=True)
    deleted_count = 0
    for image in orphaned:
        # Use storage-aware deletion (works with S3/R2 and local)
        file_name = image.file.name if hasattr(image.file, 'name') else str(image.file)
        if file_name:
            # Delete main file
            default_storage.delete(file_name)
            # Delete variants (thumb, sm, md, lg)
            base, ext = os.path.splitext(file_name)
            for suffix in ["thumb", "sm", "md", "lg"]:
                versioned_filename = f"{base}_{suffix}.webp"
                default_storage.delete(versioned_filename)
        image.delete()
        deleted_count += 1
    logger.info(f"Deleted {deleted_count} orphaned images and their variants.")

@shared_task
def cleanup_orphaned_images_task():
    return cleanup_orphaned_images()
