from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from core.authentication import JWTAuth
from core.utils.polymorphic import resolve_org_scoped_content_object
from images.api.common import logger, router
from images.api_schemas import ReorderIn
from images.models import Image, PolymorphicImageRelation
from images.schemas import DetailResponse, SetCoverIn


@router.post(
    "/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/reorder",
    response=DetailResponse,
    auth=JWTAuth(),
)
def reorder_images(
    request, org_slug: str, app_label: str, model: str, obj_id: int, data: ReorderIn
):
    resolved = resolve_org_scoped_content_object(
        request, org_slug, app_label, model, obj_id
    )
    resolved.scope.require_write()
    org = resolved.organization
    obj = resolved.obj
    ct = resolved.content_type
    user = resolved.scope.user

    rels = list(
        PolymorphicImageRelation.objects.filter(
            content_type=ct, object_id=obj.pk
        ).select_related("image")
    )
    if not rels:
        return DetailResponse(detail="ok")

    rel_by_image = {r.image_id: r for r in rels}

    provided = data.image_ids
    if len(set(provided)) != len(provided):
        raise HttpError(400, "Duplicate image ids in request")
    missing = [iid for iid in provided if iid not in rel_by_image]
    if missing:
        raise HttpError(400, "One or more image ids are not attached to this object")
    if len(provided) != len(rels):
        raise HttpError(400, "Reorder must include all currently attached image ids")

    img_org_ids = {r.image.organization_id for r in rels}
    if img_org_ids != {org.id}:
        raise HttpError(403, "One or more images do not belong to this organization")

    with transaction.atomic():
        updates = []
        for idx, image_id in enumerate(provided):
            rel = rel_by_image[image_id]
            if rel.order != idx:
                rel.order = idx
                updates.append(rel)
        if updates:
            PolymorphicImageRelation.objects.bulk_update(updates, ["order"])
        PolymorphicImageRelation.objects.filter(
            content_type=ct,
            object_id=obj.pk,
            is_cover=True,
        ).update(is_cover=False)
        if provided:
            PolymorphicImageRelation.objects.filter(
                content_type=ct,
                object_id=obj.pk,
                image_id=provided[0],
            ).update(is_cover=True)
        logger.info(
            "audit:image_reorder org=%s user=%s app=%s model=%s obj=%s images=%s",
            org.id,
            getattr(user, "id", None),
            app_label,
            model,
            obj_id,
            provided,
        )
    return DetailResponse(detail="ok")


@router.post(
    "/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/set_cover",
    response=DetailResponse,
    auth=JWTAuth(),
)
def set_cover_image(
    request, org_slug: str, app_label: str, model: str, obj_id: int, data: SetCoverIn
):
    resolved = resolve_org_scoped_content_object(
        request, org_slug, app_label, model, obj_id
    )
    resolved.scope.require_write()
    org = resolved.organization
    obj = resolved.obj
    ct = resolved.content_type
    user = resolved.scope.user

    image = get_object_or_404(Image, id=data.image_id, organization=org)
    get_object_or_404(
        PolymorphicImageRelation, image=image, content_type=ct, object_id=obj.pk
    )

    with transaction.atomic():
        qs = PolymorphicImageRelation.objects.select_for_update().filter(
            content_type=ct, object_id=obj.pk
        )
        qs.filter(is_cover=True).update(is_cover=False)
        qs.filter(image_id=data.image_id).update(is_cover=True)

    logger.info(
        "audit:image_set_cover org=%s user=%s app=%s model=%s obj=%s image=%s",
        org.id,
        getattr(user, "id", None),
        app_label,
        model,
        obj_id,
        data.image_id,
    )
    return DetailResponse(detail="ok")


@router.post(
    "/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/unset_cover",
    response=DetailResponse,
    auth=JWTAuth(),
)
def unset_cover_image(request, org_slug: str, app_label: str, model: str, obj_id: int):
    resolved = resolve_org_scoped_content_object(
        request, org_slug, app_label, model, obj_id
    )
    resolved.scope.require_write()
    org = resolved.organization
    obj = resolved.obj
    ct = resolved.content_type
    user = resolved.scope.user

    with transaction.atomic():
        qs = PolymorphicImageRelation.objects.select_for_update().filter(
            content_type=ct, object_id=obj.pk
        )
        qs.filter(is_cover=True).update(is_cover=False)

    logger.info(
        "audit:image_unset_cover org=%s user=%s app=%s model=%s obj=%s",
        org.id,
        getattr(user, "id", None),
        app_label,
        model,
        obj_id,
    )
    return DetailResponse(detail="ok")
