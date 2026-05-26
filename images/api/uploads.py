from typing import List

import images.api as image_api
from django.conf import settings
from django.db import transaction
from images.api.common import logger, router
from images.api_schemas import BulkUploadResponse
from images.models import Image
from images.schemas import ImageOut
from images.serializers import serialize_image
from images.throttles import bulk_upload_throttle, upload_throttle
from ninja import File, Status, UploadedFile
from ninja_jwt.authentication import JWTAuth


@router.post("/orgs/{org_slug}/images/", response={200: ImageOut, 400: dict}, auth=JWTAuth(), throttle=[upload_throttle])
def upload_image(request, org_slug: str, file: UploadedFile = File(...)):
    org = image_api.get_org_for_request(request, org_slug)
    user = request.user
    max_bytes = getattr(settings, "UPLOAD_IMAGE_MAX_BYTES", 10 * 1024 * 1024)
    if file.size > max_bytes:
        return Status(400, {"detail": f"File too large. Maximum allowed size is {int(max_bytes/1024/1024)}MB."})
    prefixes = getattr(settings, "UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES", ("image/",))
    if not any(str(file.content_type or "").startswith(p) for p in prefixes):
        return Status(400, {"detail": "Invalid file type. Only images are allowed."})

    filename = image_api.generate_upload_filename(f"img_{org.slug[:8]}", file.name)
    data = file.read()
    image_api.upload_to_storage(filename, data)
    try:
        variants_bytes = image_api.resize_images(data)
        base, _ext = image_api.os.path.splitext(filename)
        for key, content in variants_bytes.items():
            variant_key = f"{base}_{key}.webp"
            image_api.upload_to_storage(variant_key, content)
    except Exception as e:
        logger.warning("images:variant_generate_failed org=%s file=%s err=%s", org.id, filename, str(e))
    img = Image.objects.create(
        file=filename,
        organization=org,
        creator_id=getattr(user, "id", None),
        title=file.name,
        description="",
        alt_text="",
    )
    return serialize_image(img)


@router.post("/orgs/{org_slug}/bulk-upload/", response=List[BulkUploadResponse], auth=JWTAuth(), throttle=[bulk_upload_throttle])
def bulk_upload_images(request, org_slug: str):
    cached = image_api.read_cached_response(request)
    if cached:
        status, data = cached
        return Status(status, data) if status != 200 else data

    org = image_api.get_org_for_request(request, org_slug)
    user = request.user
    responses = []
    files = request.FILES.getlist("files")
    if not files:
        return [BulkUploadResponse(status="error", error="No files uploaded")]

    with transaction.atomic():
        for file in files:
            try:
                max_bytes = getattr(settings, "UPLOAD_IMAGE_MAX_BYTES", 10 * 1024 * 1024)
                if file.size > max_bytes:
                    responses.append(BulkUploadResponse(status="error", error="File too large", file=file.name))
                    continue
                prefixes = getattr(settings, "UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES", ("image/",))
                if not any(str(file.content_type or "").startswith(p) for p in prefixes):
                    responses.append(BulkUploadResponse(status="error", error="Invalid file type", file=file.name))
                    continue
                filename = image_api.generate_upload_filename(f"img_{org.slug[:8]}", file.name)
                data = file.read()
                image_api.upload_to_storage(filename, data)
                try:
                    variants_bytes = image_api.resize_images(data)
                    base, _ext = image_api.os.path.splitext(filename)
                    for key, content in variants_bytes.items():
                        variant_key = f"{base}_{key}.webp"
                        image_api.upload_to_storage(variant_key, content)
                except Exception as e:
                    logger.warning("images:variant_generate_failed org=%s file=%s err=%s", org.id, filename, str(e))
                img = Image.objects.create(
                    file=filename,
                    organization=org,
                    creator_id=getattr(user, "id", None),
                    title=file.name,
                    description="",
                    alt_text="",
                )
                responses.append(BulkUploadResponse(status="success", id=img.id, file=str(img.file)))
            except Exception as e:
                responses.append(BulkUploadResponse(status="error", error=str(e), file=file.name if hasattr(file, "name") else "unknown"))
    image_api.store_cached_response(request, 200, [r.model_dump() if hasattr(r, "model_dump") else r for r in responses])
    return responses
