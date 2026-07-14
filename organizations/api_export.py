import logging
from datetime import datetime
from uuid import UUID

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema, Status
from ninja.errors import HttpError

from core.authentication import JWTAuth
from core.utils.storage import generate_private_presigned_storage_url
from organizations.export_tasks import export_org_data_task
from organizations.models import ExportJob
from organizations.scope import resolve_admin_org_scope

logger = logging.getLogger(__name__)
export_router = Router(tags=["organization", "export"])


class ExportJobOut(Schema):
    id: UUID
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    error_message: str = ""
    download_url: str | None = None


def serialize_export_job(job: ExportJob) -> ExportJobOut:
    download_url = None
    if (
        job.status == ExportJob.Status.READY
        and job.object_key
        and job.expires_at
        and job.expires_at > timezone.now()
    ):
        download_url = generate_private_presigned_storage_url(
            job.object_key,
            expires_in=5 * 60,
            content_type="application/zip",
            cache_control="private, no-store",
        )
    return ExportJobOut(
        id=job.pk,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        error_message=job.error_message,
        download_url=download_url,
    )


def publish_export(job: ExportJob) -> None:
    try:
        export_org_data_task.delay(str(job.pk))
    except Exception as exc:
        job.status = ExportJob.Status.FAILED
        job.error_message = "Export could not be queued."
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "completed_at"])
        logger.exception("exports:task_publish_failed job=%s", job.pk)
        raise HttpError(503, "Export could not be queued.") from exc


@export_router.post(
    "/orgs/{org_slug}/exports/",
    response={202: ExportJobOut},
    auth=JWTAuth(),
)
def create_export(request, org_slug: str):
    scope = resolve_admin_org_scope(request, org_slug)
    job = ExportJob.objects.create(
        organization=scope.org,
        requested_by=scope.user,
    )
    publish_export(job)
    return Status(202, serialize_export_job(job))


@export_router.get(
    "/orgs/{org_slug}/exports/",
    response=list[ExportJobOut],
    auth=JWTAuth(),
)
def list_exports(request, org_slug: str):
    scope = resolve_admin_org_scope(request, org_slug)
    jobs = ExportJob.objects.filter(organization=scope.org).order_by("-created_at")[:50]
    return [serialize_export_job(job) for job in jobs]


@export_router.get(
    "/orgs/{org_slug}/exports/{job_id}/",
    response=ExportJobOut,
    auth=JWTAuth(),
)
def get_export(request, org_slug: str, job_id: UUID):
    scope = resolve_admin_org_scope(request, org_slug)
    job = get_object_or_404(ExportJob, pk=job_id, organization=scope.org)
    return serialize_export_job(job)


@export_router.post(
    "/orgs/{org_slug}/exports/{job_id}/retry/",
    response={202: ExportJobOut},
    auth=JWTAuth(),
)
def retry_export(request, org_slug: str, job_id: UUID):
    scope = resolve_admin_org_scope(request, org_slug)
    job = get_object_or_404(ExportJob, pk=job_id, organization=scope.org)
    if job.status != ExportJob.Status.FAILED:
        raise HttpError(409, "Only failed exports can be retried.")
    job.status = ExportJob.Status.PENDING
    job.started_at = None
    job.completed_at = None
    job.error_message = ""
    job.save(update_fields=["status", "started_at", "completed_at", "error_message"])
    publish_export(job)
    return Status(202, serialize_export_job(job))
