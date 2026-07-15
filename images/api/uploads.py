from typing import List

from django.conf import settings
from ninja import File, Status, UploadedFile
from ninja.errors import HttpError

from core.authentication import JWTAuth
from core.utils.idempotency import run_idempotently
from core.utils.image import InvalidImageContent
from images.api.common import get_org_scope_for_request, router
from images.api_schemas import BulkUploadResponse
from images.schemas import ImageOut
from images.serializers import serialize_image
from images.services import ImageUploadFailed, upload_image_file
from images.throttles import bulk_upload_throttle, upload_throttle


def validate_image_upload(file):
    max_bytes = getattr(settings, "UPLOAD_IMAGE_MAX_BYTES", 10 * 1024 * 1024)
    if (file.size or 0) > max_bytes:
        return f"File too large. Maximum allowed size is {int(max_bytes/1024/1024)}MB."
    prefixes = getattr(settings, "UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES", ("image/",))
    if not any(str(file.content_type or "").startswith(p) for p in prefixes):
        return "Invalid file type. Only images are allowed."
    return None


@router.post(
    "/orgs/{org_slug}/images/",
    response=ImageOut,
    auth=JWTAuth(),
    throttle=[upload_throttle],
)
def upload_image(request, org_slug: str, file: UploadedFile = File(...)):
    scope = get_org_scope_for_request(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    error = validate_image_upload(file)
    if error:
        raise HttpError(400, error)

    try:
        img = upload_image_file(file, org, creator_id=getattr(user, "id", None))
    except InvalidImageContent as exc:
        raise HttpError(400, str(exc)) from exc
    except ImageUploadFailed as exc:
        raise HttpError(503, "Image upload is temporarily unavailable.") from exc
    return serialize_image(img)


@router.post(
    "/orgs/{org_slug}/bulk-upload/",
    response=List[BulkUploadResponse],
    auth=JWTAuth(),
    throttle=[bulk_upload_throttle],
)
def bulk_upload_images(request, org_slug: str):
    scope = get_org_scope_for_request(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    files = list(request.FILES.getlist("files"))

    def perform_upload() -> tuple[int, list[dict]]:
        responses = []
        if not files:
            return 200, [
                BulkUploadResponse(
                    status="error", error="No files uploaded"
                ).model_dump()
            ]

        for file in files:
            try:
                error = validate_image_upload(file)
                if error:
                    responses.append(
                        BulkUploadResponse(status="error", error=error, file=file.name)
                    )
                    continue
                img = upload_image_file(file, org, creator_id=getattr(user, "id", None))
                responses.append(
                    BulkUploadResponse(status="success", id=img.id, file=str(img.file))
                )
            except InvalidImageContent as exc:
                responses.append(
                    BulkUploadResponse(status="error", error=str(exc), file=file.name)
                )
            except ImageUploadFailed:
                responses.append(
                    BulkUploadResponse(
                        status="error", error="Image upload failed.", file=file.name
                    )
                )
        return 200, [response.model_dump() for response in responses]

    status, data = run_idempotently(request, perform_upload)
    if status != 200:
        return Status(status, data)
    return [BulkUploadResponse.model_validate(item) for item in data]
