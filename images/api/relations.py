from typing import List

from ninja import Status
from ninja.errors import HttpError

from core.authentication import JWTAuth
from core.utils.idempotency import run_idempotently
from core.utils.polymorphic import resolve_org_scoped_content_object
from images.api.common import logger, router
from images.api_schemas import BulkImageIdsIn, ImageIdsIn
from images.operations import (
    ImageNotFoundError,
    attach_images_to_object,
    detach_images_from_object,
)
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
    try:
        result = attach_images_to_object(
            organization_id=org.id,
            target=obj,
            content_type=ct,
            image_ids=data.image_ids,
        )
    except ImageNotFoundError as exc:
        raise HttpError(404, str(exc)) from exc
    for relation in result.relations:
        if relation.image_id in result.attached_image_ids:
            logger.info(
                "audit:image_attach org=%s user=%s app=%s model=%s obj=%s image=%s rel=%s",
                org.id,
                getattr(user, "id", None),
                app_label,
                model,
                obj_id,
                relation.image_id,
                relation.id,
            )
    return [serialize_image_relation(relation) for relation in result.relations]


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
    requested_ids = list(dict.fromkeys(data.image_ids))

    def perform_attach() -> tuple[int, dict]:
        try:
            result = attach_images_to_object(
                organization_id=org.id,
                target=obj,
                content_type=ct,
                image_ids=requested_ids,
            )
        except ImageNotFoundError as exc:
            raise HttpError(
                403, "One or more images do not belong to this organization"
            ) from exc
        if result.attached_image_ids:
            logger.info(
                "audit:image_bulk_attach org=%s user=%s app=%s model=%s "
                "obj=%s attached=%s",
                org.id,
                getattr(user, "id", None),
                app_label,
                model,
                obj_id,
                result.attached_image_ids,
            )
        return 200, {"attached": result.attached_image_ids}

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
        detached = detach_images_from_object(
            target=obj,
            content_type=ct,
            image_ids=data.image_ids,
        )
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
    obj = resolved.obj
    ct = resolved.content_type
    user = resolved.scope.user
    detached = detach_images_from_object(
        target=obj,
        content_type=ct,
        image_ids=[image_id],
    )
    if not detached:
        raise HttpError(404, "Image relation not found")
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
