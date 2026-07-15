from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema, Status
from ninja.errors import HttpError

from core.authentication import JWTAuth
from core.utils.storage import generate_private_presigned_storage_url
from organizations.export_tasks import (
    enqueue_export_job,
    is_export_job_stale,
    reset_export_for_retry,
)
from organizations.models import ExportJob
from organizations.scope import resolve_admin_org_scope

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
        enqueue_export_job(job)
    except Exception as exc:
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
    with transaction.atomic():
        job = get_object_or_404(
            ExportJob.objects.select_for_update(),
            pk=job_id,
            organization=scope.org,
        )
        if job.status != ExportJob.Status.FAILED and not is_export_job_stale(job):
            raise HttpError(409, "Only failed or stale exports can be retried.")
        reset_export_for_retry(job)
    publish_export(job)
    return Status(202, serialize_export_job(job))
