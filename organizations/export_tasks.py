import json
import logging
import shutil
import tempfile
import zipfile
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from contacts.models import Contact
from core.tasks import send_email_task
from images.models import Image, PolymorphicImageRelation
from organizations.models import ExportJob, Membership
from tags.models import Tag, TaggedItem

logger = logging.getLogger(__name__)
EXPORT_PREFIX = "private/exports/"


def export_retention_days() -> int:
    return int(getattr(settings, "EXPORT_RETENTION_DAYS", 7))


def serialize_org_data(job: ExportJob) -> dict:
    org = job.organization
    memberships = Membership.objects.filter(organization=org).select_related("user")
    contacts = Contact.objects.filter(organization=org).prefetch_related(
        "tagged_items__tag"
    )
    tags = Tag.objects.filter(organization=org)
    images = Image.objects.filter(organization=org)
    tagged_items = TaggedItem.objects.filter(tag__organization=org).select_related(
        "tag", "content_type"
    )
    image_relations = PolymorphicImageRelation.objects.filter(
        image__organization=org
    ).select_related("image", "content_type")
    return {
        "format": "django-ninja-api-starter-portability-export",
        "version": 1,
        "generated_at": timezone.now().isoformat(),
        "organization": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "type": org.type,
            "created_at": org.created_at.isoformat(),
            "updated_at": org.updated_at.isoformat(),
        },
        "memberships": [
            {
                "user_id": membership.user_id,
                "email": membership.user.email,
                "username": membership.user.username,
                "role": membership.role,
            }
            for membership in memberships
        ],
        "contacts": [
            {
                "id": contact.id,
                "slug": contact.slug,
                "display_name": contact.display_name,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "email": contact.email,
                "location": contact.location,
                "phone": contact.phone,
                "notes": contact.notes,
                "avatar_path": contact.avatar_path,
                "creator_id": contact.creator_id,
                "created_at": contact.created_at.isoformat(),
                "updated_at": contact.updated_at.isoformat(),
            }
            for contact in contacts
        ],
        "tags": [{"id": tag.id, "name": tag.name, "slug": tag.slug} for tag in tags],
        "tag_relations": [
            {
                "tag_id": item.tag_id,
                "app_label": item.content_type.app_label,
                "model": item.content_type.model,
                "object_id": item.object_id,
            }
            for item in tagged_items
        ],
        "images": [
            {
                "id": image.id,
                "object_key": image.file.name,
                "title": image.title,
                "description": image.description,
                "alt_text": image.alt_text,
                "creator_id": image.creator_id,
                "created_at": image.created_at.isoformat(),
                "updated_at": image.updated_at.isoformat(),
            }
            for image in images
        ],
        "image_relations": [
            {
                "image_id": relation.image_id,
                "app_label": relation.content_type.app_label,
                "model": relation.content_type.model,
                "object_id": relation.object_id,
                "is_cover": relation.is_cover,
                "order": relation.order,
            }
            for relation in image_relations
        ],
    }


def build_export_archive(job: ExportJob, destination) -> None:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "data.json",
            json.dumps(serialize_org_data(job), ensure_ascii=False, indent=2),
        )
        for image in Image.objects.filter(organization=job.organization).iterator():
            if not image.file:
                continue
            try:
                image_name = image.file.name or str(image.file)
                with (
                    image.file.open("rb") as source,
                    archive.open(
                        f"media/{image.pk}/{image_name.rsplit('/', 1)[-1]}", "w"
                    ) as target,
                ):
                    shutil.copyfileobj(source, target, length=1024 * 1024)
            except FileNotFoundError:
                logger.warning(
                    "exports:source_media_missing job=%s image=%s", job.pk, image.pk
                )


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True)
def export_org_data_task(self, job_id: str):
    with transaction.atomic():
        job = (
            ExportJob.objects.select_for_update()
            .select_related("organization", "requested_by")
            .get(pk=job_id)
        )
        if job.status == ExportJob.Status.READY:
            return str(job.pk)
        job.status = ExportJob.Status.PROCESSING
        job.started_at = timezone.now()
        job.error_message = ""
        job.save(update_fields=["status", "started_at", "error_message"])

    object_key = f"{EXPORT_PREFIX}{job.organization_id}/{job.pk}.zip"
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip") as temporary:
            build_export_archive(job, temporary)
            temporary.seek(0)
            saved_key = default_storage.save(object_key, File(temporary))
        now = timezone.now()
        ExportJob.objects.filter(pk=job.pk).update(
            status=ExportJob.Status.READY,
            object_key=saved_key,
            completed_at=now,
            expires_at=now + timedelta(days=export_retention_days()),
            error_message="",
        )
    except Exception:
        ExportJob.objects.filter(pk=job.pk).update(
            status=ExportJob.Status.FAILED,
            completed_at=timezone.now(),
            error_message="Export generation failed.",
        )
        logger.exception("exports:generation_failed job=%s", job.pk)
        raise

    if job.requested_by is not None:
        try:
            send_email_task.delay(
                f"Your export for {job.organization.name} is ready",
                "Your export is ready. Open the app to download it before it expires.",
                [job.requested_by.email],
            )
        except Exception:
            logger.exception("exports:notification_publish_failed job=%s", job.pk)
    return str(job.pk)


@shared_task(acks_late=True, reject_on_worker_lost=True)
def cleanup_expired_exports() -> int:
    jobs = ExportJob.objects.filter(
        status=ExportJob.Status.READY,
        expires_at__lte=timezone.now(),
    )
    expired = 0
    for job in jobs.iterator():
        if job.object_key:
            try:
                default_storage.delete(job.object_key)
            except Exception:
                logger.exception("exports:retention_delete_failed job=%s", job.pk)
                continue
        job.status = ExportJob.Status.EXPIRED
        job.object_key = ""
        job.save(update_fields=["status", "object_key"])
        expired += 1
    return expired
