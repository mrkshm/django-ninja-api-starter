import hashlib
import json
from dataclasses import dataclass
from typing import List

from django.conf import settings
from ninja import File, Status, UploadedFile
from ninja.errors import HttpError

from core.authentication import JWTAuth
from core.utils.idempotency import run_idempotently
from core.utils.image import InvalidImageContent
from core.utils.uploads import UploadTooLarge, read_uploaded_file_bounded
from images.api.common import router
from images.api_schemas import BulkUploadResponse
from images.schemas import ImageOut
from images.serializers import serialize_image
from images.services import ImageUploadFailed, upload_image_file
from images.throttles import bulk_upload_throttle, upload_throttle
from organizations.scope import resolve_org_scope


@dataclass(frozen=True)
class PreparedUpload:
    name: str
    content_type: str
    data: bytes


def image_upload_max_bytes() -> int:
    return int(getattr(settings, "UPLOAD_IMAGE_MAX_BYTES", 10 * 1024 * 1024))


def validate_image_upload(file):
    max_bytes = image_upload_max_bytes()
    declared_size = getattr(file, "size", None)
    if declared_size is not None and declared_size > max_bytes:
        return f"File too large. Maximum allowed size is {int(max_bytes/1024/1024)}MB."
    prefixes = getattr(settings, "UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES", ("image/",))
    if not any(str(file.content_type or "").startswith(p) for p in prefixes):
        return "Invalid file type. Only images are allowed."
    return None


def _read_prepared_upload(file, *, max_bytes: int) -> PreparedUpload:
    try:
        data = read_uploaded_file_bounded(file, max_bytes=max_bytes)
    except UploadTooLarge as exc:
        raise HttpError(400, "Image upload exceeds the configured size limit.") from exc
    return PreparedUpload(
        name=str(getattr(file, "name", "") or "image"),
        content_type=str(getattr(file, "content_type", "") or ""),
        data=data,
    )


def _multipart_fingerprint(files: list[PreparedUpload]) -> str:
    """Hash ordered multipart metadata and bytes using a versioned format."""
    digest = hashlib.sha256()
    digest.update(b"image-bulk-upload-v1\0")
    for index, file in enumerate(files):
        metadata = json.dumps(
            {
                "field": "files",
                "index": index,
                "name": file.name,
                "content_type": file.content_type,
                "size": len(file.data),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        digest.update(len(metadata).to_bytes(8, "big"))
        digest.update(metadata)
        digest.update(len(file.data).to_bytes(8, "big"))
        digest.update(file.data)
    return digest.hexdigest()


def _prepare_bulk_uploads(files) -> list[PreparedUpload]:
    max_files = int(getattr(settings, "UPLOAD_IMAGE_MAX_FILES_PER_REQUEST", 20))
    max_total = int(getattr(settings, "UPLOAD_IMAGE_MAX_TOTAL_BYTES", 50 * 1024 * 1024))
    per_file = image_upload_max_bytes()
    if len(files) > max_files:
        raise HttpError(400, f"Upload at most {max_files} images per request.")

    declared_total = sum(
        size for file in files if (size := getattr(file, "size", None)) is not None
    )
    if declared_total > max_total:
        raise HttpError(400, "Image upload exceeds the aggregate size limit.")

    prepared = []
    total = 0
    for file in files:
        declared_size = getattr(file, "size", None)
        if declared_size is not None and declared_size > per_file:
            raise HttpError(400, "Image upload exceeds the per-file size limit.")
        remaining = max_total - total
        if remaining <= 0:
            raise HttpError(400, "Image upload exceeds the aggregate size limit.")
        limit = min(per_file, remaining)
        try:
            item = _read_prepared_upload(file, max_bytes=limit)
        except HttpError as exc:
            if remaining < per_file:
                raise HttpError(
                    400, "Image upload exceeds the aggregate size limit."
                ) from exc
            raise
        prepared.append(item)
        total += len(item.data)
    return prepared


def _request_upload_files(request) -> list:
    files = request.FILES
    if hasattr(files, "getlist"):
        return list(files.getlist("files"))
    value = files.get("files", [])
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value] if value else []


@router.post(
    "/orgs/{org_slug}/images/",
    response=ImageOut,
    auth=JWTAuth(),
    throttle=[upload_throttle],
)
def upload_image(request, org_slug: str, file: UploadedFile = File(...)):
    scope = resolve_org_scope(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    error = validate_image_upload(file)
    if error:
        raise HttpError(400, error)

    try:
        prepared = _read_prepared_upload(file, max_bytes=image_upload_max_bytes())
        img = upload_image_file(
            prepared.data,
            org,
            original_name=prepared.name,
            creator_id=getattr(user, "id", None),
        )
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
    scope = resolve_org_scope(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    files = _request_upload_files(request)
    if not files:
        return [BulkUploadResponse(status="error", error="No files uploaded")]
    prepared_files = _prepare_bulk_uploads(files)
    fingerprint = _multipart_fingerprint(prepared_files)

    def perform_upload() -> tuple[int, list[dict]]:
        responses = []
        for file, prepared in zip(files, prepared_files, strict=True):
            try:
                error = validate_image_upload(file)
                if error:
                    responses.append(
                        BulkUploadResponse(status="error", error=error, file=file.name)
                    )
                    continue
                img = upload_image_file(
                    prepared.data,
                    org,
                    original_name=prepared.name,
                    creator_id=getattr(user, "id", None),
                )
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

    status, data = run_idempotently(
        request, perform_upload, request_fingerprint=fingerprint
    )
    if status != 200:
        return Status(status, data)
    return [BulkUploadResponse.model_validate(item) for item in data]
