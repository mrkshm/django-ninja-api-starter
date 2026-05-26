import json

import images.api as image_api
from django.db import transaction
from django.shortcuts import get_object_or_404
from images.api.common import logger, router
from images.models import Image, PolymorphicImageRelation
from images.throttles import bulk_delete_throttle
from ninja import Status
from ninja_jwt.authentication import JWTAuth


@router.delete("/orgs/{org_slug}/images/{image_id}/", auth=JWTAuth(), response={204: None})
def delete_image(request, org_slug: str, image_id: int):
    org = image_api.get_org_for_request(request, org_slug)
    image = get_object_or_404(Image, id=image_id, organization=org)
    PolymorphicImageRelation.objects.filter(image=image).delete()
    base, _ext = image_api.os.path.splitext(image.file.name if hasattr(image.file, "name") else image.file)
    for suffix in ["thumb", "sm", "md", "lg"]:
        versioned_filename = f"{base}_{suffix}.webp"
        image_api.default_storage.delete(versioned_filename)
    image_api.default_storage.delete(image.file.name if hasattr(image.file, "name") else image.file)
    image.delete()
    logger.info(
        "audit:image_delete org=%s user=%s image=%s",
        org.id, getattr(request.user, "id", None), image_id,
    )
    return Status(204, None)


@router.post("/orgs/{org_slug}/bulk-delete/", response={204: None, 400: dict}, auth=JWTAuth(), throttle=[bulk_delete_throttle])
def bulk_delete_images(request, org_slug: str):
    cached = image_api.read_cached_response(request)
    if cached:
        status, data = cached
        return Status(status, data)

    org = image_api.get_org_for_request(request, org_slug)
    user = request.user
    try:
        data = request.POST.dict() if request.POST else {}
        if not data and request.body:
            data = json.loads(request.body.decode("utf-8"))

        ids = data.get("ids", [])
        if not ids:
            return Status(400, {"detail": "No ids provided for deletion"})

        with transaction.atomic():
            for img_id in ids:
                try:
                    image = Image.objects.get(id=img_id, organization=org)
                    image.delete()
                    logger.info(
                        "audit:image_delete org=%s user=%s image=%s",
                        org.id, getattr(user, "id", None), img_id,
                    )
                except Exception:
                    continue
        image_api.store_cached_response(request, 204, None)
        return Status(204, None)

    except json.JSONDecodeError:
        return Status(400, {"detail": "Invalid JSON data"})
    except Exception as e:
        return Status(400, {"detail": str(e)})
