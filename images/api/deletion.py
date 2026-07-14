import json
import os

from core.utils.idempotency import read_cached_response, store_cached_response
from django.core.files.storage import default_storage
from django.db import transaction
from django.shortcuts import get_object_or_404
from images.api.common import get_org_scope_for_request, logger, router
from images.models import Image, PolymorphicImageRelation
from images.throttles import bulk_delete_throttle
from ninja import Status
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth


@router.delete("/orgs/{org_slug}/images/{image_id}/", auth=JWTAuth(), response={204: None})
def delete_image(request, org_slug: str, image_id: int):
    scope = get_org_scope_for_request(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    image = get_object_or_404(Image, id=image_id, organization=org)
    PolymorphicImageRelation.objects.filter(image=image).delete()
    file_name = image.file.name or str(image.file) if hasattr(image.file, "name") else str(image.file)
    base, _ext = os.path.splitext(file_name)
    for suffix in ["thumb", "sm", "md", "lg"]:
        versioned_filename = f"{base}_{suffix}.webp"
        default_storage.delete(versioned_filename)
    default_storage.delete(file_name)
    image.delete()
    logger.info(
        "audit:image_delete org=%s user=%s image=%s",
        org.id, getattr(user, "id", None), image_id,
    )
    return Status(204, None)


@router.post("/orgs/{org_slug}/bulk-delete/", response={204: None, 400: dict}, auth=JWTAuth(), throttle=[bulk_delete_throttle])
def bulk_delete_images(request, org_slug: str):
    cached = read_cached_response(request)
    if cached:
        status, data = cached
        return Status(status, data)

    scope = get_org_scope_for_request(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    try:
        data = request.POST.dict() if request.POST else {}
        if not data and request.body:
            data = json.loads(request.body.decode("utf-8"))

        ids = data.get("ids", [])
        if not ids:
            raise HttpError(400, "No ids provided for deletion")

        deleted_ids = []
        failed = []
        with transaction.atomic():
            for img_id in ids:
                try:
                    image = Image.objects.get(id=img_id, organization=org)
                except Image.DoesNotExist:
                    failed.append({"id": img_id, "reason": "not found"})
                    continue

                try:
                    image.delete()
                except Exception as exc:
                    failed.append({"id": img_id, "reason": str(exc)})
                    continue

                deleted_ids.append(img_id)
                logger.info(
                    "audit:image_delete org=%s user=%s image=%s",
                    org.id, getattr(user, "id", None), img_id,
                )

        if failed:
            status = 400
            data = {
                "detail": "Some images could not be deleted" if deleted_ids else "No images were deleted",
                "deleted": deleted_ids,
                "failed": failed,
            }
            store_cached_response(request, status, data)
            return Status(status, data)

        store_cached_response(request, 204, None)
        return Status(204, None)

    except json.JSONDecodeError:
        raise HttpError(400, "Invalid JSON data")
    except HttpError:
        raise
    except Exception as e:
        raise HttpError(400, str(e))
