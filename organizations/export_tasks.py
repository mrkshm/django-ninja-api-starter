import hashlib
import logging
import tempfile
import threading
import time
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

from core.tasks import send_email_task
from organizations.export_archive import build_export_archive
from organizations.models import ExportJob

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
                build_export_archive(
                    job,
                    temporary.file,
                    heartbeat=_heartbeat(job.pk),
                )
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
