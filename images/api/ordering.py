from ninja.errors import HttpError

from core.authentication import JWTAuth
from core.utils.polymorphic import resolve_org_scoped_content_object
from images.api.common import logger, router
from images.api_schemas import ReorderIn
from images.operations import (
    ImageNotFoundError,
    ImageOperationError,
    ImageOwnershipError,
    reorder_object_images,
    set_object_cover_image,
    unset_object_cover_image,
)
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

    provided = data.image_ids
    try:
        reorder_object_images(
            organization_id=org.id,
            target=obj,
            content_type=ct,
            image_ids=provided,
        )
    except ImageOwnershipError as exc:
        raise HttpError(403, str(exc)) from exc
    except ImageOperationError as exc:
        raise HttpError(400, str(exc)) from exc
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

    try:
        set_object_cover_image(
            organization_id=org.id,
            target=obj,
            content_type=ct,
            image_id=data.image_id,
        )
    except ImageNotFoundError as exc:
        raise HttpError(404, str(exc)) from exc

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

    unset_object_cover_image(target=obj, content_type=ct)

    logger.info(
        "audit:image_unset_cover org=%s user=%s app=%s model=%s obj=%s",
        org.id,
        getattr(user, "id", None),
        app_label,
        model,
        obj_id,
    )
    return DetailResponse(detail="ok")
