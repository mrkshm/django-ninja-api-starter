import hashlib
import json
import logging
import shutil
import tempfile
import threading
import time
import zipfile
from contextlib import contextmanager
from datetime import timedelta
from typing import Callable

from celery import shared_task
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from contacts.models import Contact
from core.tasks import send_email_task
from images.models import Image, PolymorphicImageRelation
from organizations.models import ExportJob, Membership
from tags.models import Tag, TaggedItem

logger = logging.getLogger(__name__)
EXPORT_PREFIX = "private/exports/"
HEARTBEAT_INTERVAL_SECONDS = 30
_local_export_locks: dict[str, threading.Lock] = {}
_local_export_locks_guard = threading.Lock()


def export_retention_days() -> int:
    return int(getattr(settings, "EXPORT_RETENTION_DAYS", 7))


def export_stale_after_seconds() -> int:
    return int(getattr(settings, "EXPORT_STALE_AFTER_SECONDS", 35 * 60))


def is_export_job_stale(job: ExportJob, *, now=None) -> bool:
    now = now or timezone.now()
    cutoff = now - timedelta(seconds=export_stale_after_seconds())
    if job.status == ExportJob.Status.PENDING:
        activity_at = job.queued_at or job.created_at
    elif job.status == ExportJob.Status.PROCESSING:
        activity_at = (
            job.heartbeat_at or job.started_at or job.queued_at or job.created_at
        )
    else:
        return False
    return activity_at <= cutoff


def reset_export_for_retry(job: ExportJob, *, now=None) -> None:
    now = now or timezone.now()
    job.status = ExportJob.Status.PENDING
    job.queued_at = now
    job.started_at = None
    job.heartbeat_at = None
    job.completed_at = None
    job.expires_at = None
    job.error_message = ""
    job.save(
        update_fields=[
            "status",
            "queued_at",
            "started_at",
            "heartbeat_at",
            "completed_at",
            "expires_at",
            "error_message",
        ]
    )


def enqueue_export_job(job: ExportJob) -> None:
    queued_at = timezone.now()
    updated = ExportJob.objects.filter(
        pk=job.pk, status=ExportJob.Status.PENDING
    ).update(queued_at=queued_at)
    if updated != 1:
        raise RuntimeError("Only pending exports can be queued.")
    job.queued_at = queued_at
    try:
        export_org_data_task.delay(str(job.pk))
    except Exception:
        completed_at = timezone.now()
        ExportJob.objects.filter(pk=job.pk, status=ExportJob.Status.PENDING).update(
            status=ExportJob.Status.FAILED,
            completed_at=completed_at,
            error_message="Export could not be queued.",
        )
        job.status = ExportJob.Status.FAILED
        job.completed_at = completed_at
        job.error_message = "Export could not be queued."
        logger.exception("exports:task_publish_failed job=%s", job.pk)
        raise


def _advisory_lock_id(job_id: str) -> int:
    digest = hashlib.blake2b(str(job_id).encode(), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


@contextmanager
def export_job_lock(job_id: str):
    """Hold a session lock for the complete export, not only state transitions."""
    if connection.vendor == "postgresql":
        lock_id = _advisory_lock_id(job_id)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_id])
            acquired = cursor.fetchone()[0]
        try:
            yield acquired
        finally:
            if acquired:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
        return

    # SQLite is used in tests and local development. Process-local locking mirrors
    # the production ownership semantics closely enough for those environments.
    with _local_export_locks_guard:
        lock = _local_export_locks.setdefault(str(job_id), threading.Lock())
    acquired = lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()


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


def build_export_archive(
    job: ExportJob,
    destination,
    heartbeat: Callable[[], None] | None = None,
) -> None:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "data.json",
            json.dumps(serialize_org_data(job), ensure_ascii=False, indent=2),
        )
        if heartbeat:
            heartbeat()
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
            if heartbeat:
                heartbeat()


def _heartbeat(job_id) -> Callable[[], None]:
    last_heartbeat = 0.0

    def update() -> None:
        nonlocal last_heartbeat
        monotonic_now = time.monotonic()
        if monotonic_now - last_heartbeat < HEARTBEAT_INTERVAL_SECONDS:
            return
        ExportJob.objects.filter(pk=job_id, status=ExportJob.Status.PROCESSING).update(
            heartbeat_at=timezone.now()
        )
        last_heartbeat = monotonic_now

    return update


def _mark_export_ready(job: ExportJob, object_key: str) -> None:
    now = timezone.now()
    updated = ExportJob.objects.filter(
        pk=job.pk, status=ExportJob.Status.PROCESSING
    ).update(
        status=ExportJob.Status.READY,
        object_key=object_key,
        heartbeat_at=now,
        completed_at=now,
        expires_at=now + timedelta(days=export_retention_days()),
        error_message="",
    )
    if updated != 1:
        raise RuntimeError("Export job no longer belongs to this worker.")


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True)
def export_org_data_task(self, job_id: str):
    with export_job_lock(job_id) as acquired:
        if not acquired:
            logger.info("exports:already_running job=%s", job_id)
            return str(job_id)

        with transaction.atomic():
            job = (
                ExportJob.objects.select_for_update()
                .select_related("organization", "requested_by")
                .get(pk=job_id)
            )
            if job.status in {
                ExportJob.Status.READY,
                ExportJob.Status.FAILED,
                ExportJob.Status.EXPIRED,
            }:
                return str(job.pk)
            now = timezone.now()
            job.status = ExportJob.Status.PROCESSING
            job.started_at = now
            job.heartbeat_at = now
            job.completed_at = None
            job.expires_at = None
            job.error_message = ""
            job.attempt_count += 1
            job.save(
                update_fields=[
                    "status",
                    "started_at",
                    "heartbeat_at",
                    "completed_at",
                    "expires_at",
                    "error_message",
                    "attempt_count",
                ]
            )

        object_key = f"{EXPORT_PREFIX}{job.organization_id}/{job.pk}.zip"
        saved_key = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip") as temporary:
                build_export_archive(job, temporary, heartbeat=_heartbeat(job.pk))
                temporary.seek(0)
                for stale_key in {job.object_key, object_key} - {""}:
                    default_storage.delete(stale_key)
                candidate_key = default_storage.save(object_key, File(temporary))
                if candidate_key != object_key:
                    default_storage.delete(candidate_key)
                    raise RuntimeError("Export storage changed the deterministic key.")
                saved_key = candidate_key
            _mark_export_ready(job, saved_key)
        except Exception:
            if saved_key:
                try:
                    default_storage.delete(saved_key)
                except Exception:
                    logger.exception(
                        "exports:failed_upload_cleanup_failed job=%s key=%s",
                        job.pk,
                        saved_key,
                    )
            ExportJob.objects.filter(
                pk=job.pk, status=ExportJob.Status.PROCESSING
            ).update(
                status=ExportJob.Status.FAILED,
                heartbeat_at=timezone.now(),
                completed_at=timezone.now(),
                error_message="Export generation failed.",
            )
            logger.exception("exports:generation_failed job=%s", job.pk)
            raise

        if job.requested_by is not None:
            try:
                send_email_task.delay(
                    f"Your export for {job.organization.name} is ready",
                    (
                        "Your export is ready. Open the app to download it "
                        "before it expires."
                    ),
                    [job.requested_by.email],
                )
            except Exception:
                logger.exception("exports:notification_publish_failed job=%s", job.pk)
        return str(job.pk)


def _stale_export_query(cutoff):
    pending = Q(status=ExportJob.Status.PENDING) & (
        Q(queued_at__lte=cutoff) | Q(queued_at__isnull=True, created_at__lte=cutoff)
    )
    processing = Q(status=ExportJob.Status.PROCESSING) & (
        Q(heartbeat_at__lte=cutoff)
        | Q(heartbeat_at__isnull=True, started_at__lte=cutoff)
        | Q(
            heartbeat_at__isnull=True,
            started_at__isnull=True,
            queued_at__lte=cutoff,
        )
        | Q(
            heartbeat_at__isnull=True,
            started_at__isnull=True,
            queued_at__isnull=True,
            created_at__lte=cutoff,
        )
    )
    return pending | processing


@shared_task(acks_late=True, reject_on_worker_lost=True)
def recover_stale_exports() -> int:
    now = timezone.now()
    cutoff = now - timedelta(seconds=export_stale_after_seconds())
    job_ids = list(
        ExportJob.objects.filter(_stale_export_query(cutoff)).values_list(
            "pk", flat=True
        )
    )
    recovered = 0
    for job_id in job_ids:
        with transaction.atomic():
            job = ExportJob.objects.select_for_update().filter(pk=job_id).first()
            if job is None or not is_export_job_stale(job, now=now):
                continue
            reset_export_for_retry(job, now=now)
        try:
            enqueue_export_job(job)
        except Exception:
            continue
        recovered += 1
    return recovered


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
