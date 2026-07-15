from typing import List

from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Status
from ninja.errors import HttpError

from core.authentication import JWTAuth
from core.utils.idempotency import run_idempotently
from core.utils.polymorphic import resolve_org_scoped_content_object
from images.api.common import logger, router
from images.api_schemas import BulkImageIdsIn, ImageIdsIn
from images.models import Image, PolymorphicImageRelation
from images.schemas import BulkAttachOut, BulkDetachOut, PolymorphicImageRelationOut
from images.serializers import serialize_image_relation
from images.throttles import bulk_attach_throttle, bulk_detach_throttle


@router.post(
    "/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/",
    response=List[PolymorphicImageRelationOut],
    auth=JWTAuth(),
)
def attach_images(
    request, org_slug: str, app_label: str, model: str, obj_id: int, data: ImageIdsIn
):
    resolved = resolve_org_scoped_content_object(
        request, org_slug, app_label, model, obj_id
    )
    resolved.scope.require_write()
    org = resolved.organization
    obj = resolved.obj
    ct = resolved.content_type
    user = resolved.scope.user
    out = []
    with transaction.atomic():
        obj.__class__.objects.select_for_update().only("pk").get(pk=obj.pk)
        rel_qs = PolymorphicImageRelation.objects.select_for_update().filter(
            content_type=ct, object_id=obj.pk
        )
        has_primary = rel_qs.filter(is_cover=True).exists()
        existing_orders = [
            order
            for order in rel_qs.exclude(order__isnull=True).values_list(
                "order", flat=True
            )
            if order is not None
        ]
        next_order = (max(existing_orders) + 1) if existing_orders else 0
        for image_id in data.image_ids:
            image = get_object_or_404(Image, id=image_id, organization=org)
            rel, created = PolymorphicImageRelation.objects.get_or_create(
                image=image,
                content_type=ct,
                object_id=obj.pk,
            )
            if created:
                if rel.order is None:
                    rel.order = next_order
                    next_order += 1
                if not has_primary:
                    rel.is_cover = True
                    has_primary = True
                rel.save(update_fields=["order", "is_cover"])
                logger.info(
                    "audit:image_attach org=%s user=%s app=%s model=%s obj=%s image=%s rel=%s",
                    org.id,
                    getattr(user, "id", None),
                    app_label,
                    model,
                    obj_id,
                    image.id,
                    rel.id,
                )
            out.append(serialize_image_relation(rel))
    return out


@router.post(
    "/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_attach/",
    response=BulkAttachOut,
    auth=JWTAuth(),
    throttle=[bulk_attach_throttle],
)
def bulk_attach_images(
    request,
    org_slug: str,
    app_label: str,
    model: str,
    obj_id: int,
    data: BulkImageIdsIn,
):
    resolved = resolve_org_scoped_content_object(
        request, org_slug, app_label, model, obj_id
    )
    resolved.scope.require_write()
    org = resolved.organization
    obj = resolved.obj
    ct = resolved.content_type
    user = resolved.scope.user
    requested_ids = set(data.image_ids)

    def perform_attach() -> tuple[int, dict]:
        images = list(Image.objects.filter(id__in=requested_ids, organization=org))
        found_ids = {image.id for image in images}
        missing = requested_ids - found_ids
        if missing:
            raise HttpError(
                403, "One or more images do not belong to this organization"
            )
        attached = []
        obj.__class__.objects.select_for_update().only("pk").get(pk=obj.pk)
        rel_qs = PolymorphicImageRelation.objects.select_for_update().filter(
            content_type=ct, object_id=obj.pk
        )
        has_primary = rel_qs.filter(is_cover=True).exists()
        existing_orders = [
            order
            for order in rel_qs.exclude(order__isnull=True).values_list(
                "order", flat=True
            )
            if order is not None
        ]
        next_order = (max(existing_orders) + 1) if existing_orders else 0
        for image in images:
            rel, created = PolymorphicImageRelation.objects.get_or_create(
                image=image,
                content_type=ct,
                object_id=obj.pk,
            )
            if created:
                if rel.order is None:
                    rel.order = next_order
                    next_order += 1
                if not has_primary:
                    rel.is_cover = True
                    has_primary = True
                rel.save(update_fields=["order", "is_cover"])
                attached.append(image.id)
        if attached:
            logger.info(
                "audit:image_bulk_attach org=%s user=%s app=%s model=%s "
                "obj=%s attached=%s",
                org.id,
                getattr(user, "id", None),
                app_label,
                model,
                obj_id,
                attached,
            )
        return 200, {"attached": attached}

    status, response_data = run_idempotently(request, perform_attach)
    return Status(status, response_data) if status != 200 else response_data


@router.post(
    "/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_detach/",
    response=BulkDetachOut,
    auth=JWTAuth(),
    throttle=[bulk_detach_throttle],
)
def bulk_detach_images(
    request,
    org_slug: str,
    app_label: str,
    model: str,
    obj_id: int,
    data: BulkImageIdsIn,
):
    resolved = resolve_org_scoped_content_object(
        request, org_slug, app_label, model, obj_id
    )
    resolved.scope.require_write()
    org = resolved.organization
    obj = resolved.obj
    ct = resolved.content_type
    user = resolved.scope.user

    def perform_detach() -> tuple[int, dict]:
        images = Image.objects.filter(id__in=data.image_ids, organization=org)
        detached = []
        for image in images:
            deleted, _ = PolymorphicImageRelation.objects.filter(
                image=image,
                content_type=ct,
                object_id=obj.pk,
            ).delete()
            if deleted:
                detached.append(image.id)
        if detached:
            logger.info(
                "audit:image_bulk_detach org=%s user=%s app=%s model=%s "
                "obj=%s detached=%s",
                org.id,
                getattr(user, "id", None),
                app_label,
                model,
                obj_id,
                detached,
            )
        return 200, {"detached": detached}

    status, response_data = run_idempotently(request, perform_detach)
    return Status(status, response_data) if status != 200 else response_data


@router.delete(
    "/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/{image_id}/",
    auth=JWTAuth(),
    response={204: None},
)
def remove_image_from_object(
    request, org_slug: str, app_label: str, model: str, obj_id: int, image_id: int
):
    resolved = resolve_org_scoped_content_object(
        request, org_slug, app_label, model, obj_id
    )
    resolved.scope.require_write()
    org = resolved.organization
    ct = resolved.content_type
    user = resolved.scope.user
    rel = get_object_or_404(
        PolymorphicImageRelation, image_id=image_id, content_type=ct, object_id=obj_id
    )
    rel.delete()
    logger.info(
        "audit:image_detach org=%s user=%s app=%s model=%s obj=%s image=%s",
        org.id,
        getattr(user, "id", None),
        app_label,
        model,
        obj_id,
        image_id,
    )
    return Status(204, None)
