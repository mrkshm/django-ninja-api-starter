from typing import List

from core.utils.polymorphic import resolve_org_scoped_content_object
from images.api.common import get_org_scope_for_request, router
from images.models import Image, PolymorphicImageRelation
from images.schemas import ImageOut, PolymorphicImageRelationOut
from images.serializers import serialize_image, serialize_image_relation
from ninja.errors import HttpError
from ninja.pagination import LimitOffsetPagination, paginate
from ninja_jwt.authentication import JWTAuth


@router.get("/orgs/{org_slug}/images/", response=List[ImageOut], auth=JWTAuth())
@paginate(LimitOffsetPagination)
def list_images_for_org(request, org_slug: str, ordering: str | None = None):
    scope = get_org_scope_for_request(request, org_slug)
    ordering_map = {
        None: "-created_at",
        "created_at": "created_at",
        "-created_at": "-created_at",
        "title": "title",
        "-title": "-title",
    }
    if ordering not in ordering_map:
        raise HttpError(400, "Invalid ordering. Allowed: created_at, -created_at, title, -title")
    return [
        serialize_image(image)
        for image in Image.objects.filter(organization=scope.org).order_by(ordering_map[ordering])
    ]


@router.get("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/", response=List[PolymorphicImageRelationOut], auth=JWTAuth())
@paginate(LimitOffsetPagination)
def list_images_for_object(request, org_slug: str, app_label: str, model: str, obj_id: int, ordering: str | None = None):
    resolved = resolve_org_scoped_content_object(request, org_slug, app_label, model, obj_id)
    ct = resolved.content_type
    ordering_map = {
        None: "order",
        "order": "order",
        "-order": "-order",
        "created_at": "image__created_at",
        "-created_at": "-image__created_at",
        "title": "image__title",
        "-title": "-image__title",
    }
    if ordering not in ordering_map:
        raise HttpError(400, "Invalid ordering. Allowed: created_at, -created_at, title, -title")
    relations = (
        PolymorphicImageRelation.objects
        .filter(content_type=ct, object_id=obj_id)
        .select_related("image")
        .order_by(ordering_map[ordering], "pk")
    )
    return [serialize_image_relation(relation) for relation in relations]
