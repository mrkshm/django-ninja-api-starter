from typing import List

from django.conf import settings
from django.db import transaction
from core.utils.idempotency import read_cached_response, store_cached_response
from images.api.common import get_org_scope_for_request, router
from images.api_schemas import BulkUploadResponse
from images.schemas import ImageOut
from images.serializers import serialize_image
from images.services import upload_image_file
from images.throttles import bulk_upload_throttle, upload_throttle
from ninja import File, Status, UploadedFile
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth


def validate_image_upload(file):
    max_bytes = getattr(settings, "UPLOAD_IMAGE_MAX_BYTES", 10 * 1024 * 1024)
    if file.size > max_bytes:
        return f"File too large. Maximum allowed size is {int(max_bytes/1024/1024)}MB."
    prefixes = getattr(settings, "UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES", ("image/",))
    if not any(str(file.content_type or "").startswith(p) for p in prefixes):
        return "Invalid file type. Only images are allowed."
    return None


@router.post("/orgs/{org_slug}/images/", response=ImageOut, auth=JWTAuth(), throttle=[upload_throttle])
def upload_image(request, org_slug: str, file: UploadedFile = File(...)):
    scope = get_org_scope_for_request(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    error = validate_image_upload(file)
    if error:
        raise HttpError(400, error)

    img = upload_image_file(file, org, creator_id=getattr(user, "id", None))
    return serialize_image(img)


@router.post("/orgs/{org_slug}/bulk-upload/", response=List[BulkUploadResponse], auth=JWTAuth(), throttle=[bulk_upload_throttle])
def bulk_upload_images(request, org_slug: str):
    cached = read_cached_response(request)
    if cached:
        status, data = cached
        return Status(status, data) if status != 200 else data

    scope = get_org_scope_for_request(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    responses = []
    files = request.FILES.getlist("files")
    if not files:
        return [BulkUploadResponse(status="error", error="No files uploaded")]

    with transaction.atomic():
        for file in files:
            try:
                error = validate_image_upload(file)
                if error:
                    responses.append(BulkUploadResponse(status="error", error=error, file=file.name))
                    continue
                img = upload_image_file(file, org, creator_id=getattr(user, "id", None))
                responses.append(BulkUploadResponse(status="success", id=img.id, file=str(img.file)))
            except Exception as e:
                responses.append(BulkUploadResponse(status="error", error=str(e), file=file.name if hasattr(file, "name") else "unknown"))
    store_cached_response(request, 200, [r.model_dump() if hasattr(r, "model_dump") else r for r in responses])
    return responses
