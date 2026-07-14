import json

from core.utils.idempotency import read_cached_response, store_cached_response
from django.db import transaction
from django.shortcuts import get_object_or_404
from images.api.common import get_org_scope_for_request, logger, router
from images.models import Image
from images.services import delete_image_record
from images.throttles import bulk_delete_throttle
from ninja import Status
from ninja.errors import HttpError
from core.authentication import JWTAuth


@router.delete(
    "/orgs/{org_slug}/images/{image_id}/", auth=JWTAuth(), response={204: None}
)
def delete_image(request, org_slug: str, image_id: int):
    scope = get_org_scope_for_request(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    image = get_object_or_404(Image, id=image_id, organization=org)
    delete_image_record(image)
    logger.info(
        "audit:image_delete org=%s user=%s image=%s",
        org.id,
        getattr(user, "id", None),
        image_id,
    )
    return Status(204, None)


@router.post(
    "/orgs/{org_slug}/bulk-delete/",
    response={204: None, 400: dict},
    auth=JWTAuth(),
    throttle=[bulk_delete_throttle],
)
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
                    delete_image_record(image)
                except Exception:
                    failed.append({"id": img_id, "reason": "delete failed"})
                    continue

                deleted_ids.append(img_id)
                logger.info(
                    "audit:image_delete org=%s user=%s image=%s",
                    org.id,
                    getattr(user, "id", None),
                    img_id,
                )

        if failed:
            status = 400
            data = {
                "detail": (
                    "Some images could not be deleted"
                    if deleted_ids
                    else "No images were deleted"
                ),
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
    except Exception as exc:
        logger.exception("images:bulk_delete_failed org=%s", org.id)
        raise HttpError(500, "Image deletion failed.") from exc
