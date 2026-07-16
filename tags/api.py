import logging

from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import LimitOffsetPagination, paginate

from core.authentication import JWTAuth
from core.utils.polymorphic import resolve_org_scoped_content_object
from organizations.scope import resolve_org_scope
from tags.models import Tag
from tags.schemas import (
    DetailResponse,
    RemovedCountResponse,
    TagAssignment,
    TagCreate,
    TagOut,
    TagUpdate,
)
from tags.services import (
    assign_tags_to_object,
)
from tags.services import create_tag as create_tag_service
from tags.services import delete_tag as delete_tag_service
from tags.services import (
    rename_tag,
    unassign_tag_from_object_by_slug,
    unassign_tags_from_object,
)

# Module-level router and logger
router = Router(tags=["tags"])
logger = logging.getLogger("audit")

TAG_ASSIGN_DESCRIPTION = (
    "Assign up to 50 tag names to an organization-scoped object. "
    "Missing tags are created in that organization."
)
TAG_OBJECT_DESCRIPTION = "Manage tags attached to a polymorphic object identified by app label, model name, and object id."


@router.get(
    "/orgs/{org_slug}/tags/",
    response=list[TagOut],
    auth=JWTAuth(),
    summary="List organization tags",
    description="Return the paginated tag list for an organization. Supports ordering by name or id.",
)
@paginate(LimitOffsetPagination)
def list_tags(request, org_slug: str, ordering: str | None = None):
    scope = resolve_org_scope(request, org_slug)
    ordering_map = {
        None: "name",
        "name": "name",
        "-name": "-name",
        "id": "id",
        "-id": "-id",
    }
    if ordering not in ordering_map:
        raise HttpError(400, "Invalid ordering. Allowed: name, -name, id, -id")
    return Tag.objects.filter(organization=scope.org).order_by(ordering_map[ordering])


@router.get(
    "/orgs/{org_slug}/tags/search/",
    response=list[TagOut],
    auth=JWTAuth(),
    summary="Search organization tags",
    description="Search tags in an organization by case-insensitive partial name.",
)
@paginate(LimitOffsetPagination)
def search_tags(request, org_slug: str, q: str | None = None):
    """
    Search for tags in an organization by name.
    """
    scope = resolve_org_scope(request, org_slug)
    queryset = Tag.objects.filter(organization=scope.org)
    if q:
        queryset = queryset.filter(name__icontains=q)
    return queryset.order_by("name")


@router.get(
    "/orgs/{org_slug}/tags/by-slug/{slug}/",
    response=TagOut,
    auth=JWTAuth(),
    summary="Get tag by slug",
    description="Return one tag from an organization by its slug.",
)
def get_tag_by_slug(request, org_slug: str, slug: str):
    scope = resolve_org_scope(request, org_slug)
    tag = get_object_or_404(Tag, slug=slug, organization=scope.org)
    return TagOut.model_validate(tag)


@router.post(
    "/orgs/{org_slug}/tags/",
    response=TagOut,
    auth=JWTAuth(),
    summary="Create tag",
    description="Create a tag in an organization. Tag names must be unique within that organization.",
)
def create_tag(request, org_slug: str, data: TagCreate):
    scope = resolve_org_scope(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    name = data.name
    tag = create_tag_service(org, name)
    logger.info(
        "audit:tag_create org=%s user=%s tag_id=%s name=%s",
        org.id,
        getattr(user, "id", None),
        tag.id,
        tag.name,
    )
    return tag


@router.get(
    "/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/",
    response=list[TagOut],
    auth=JWTAuth(),
    summary="List object tags",
    description=TAG_OBJECT_DESCRIPTION,
)
@paginate(LimitOffsetPagination)
def list_tags_for_object(
    request,
    org_slug: str,
    app_label: str,
    model: str,
    obj_id: int,
    ordering: str | None = None,
):
    """List tags for a specific object (paginated)."""
    resolved = resolve_org_scoped_content_object(
        request, org_slug, app_label, model, obj_id
    )
    org = resolved.organization
    ct = resolved.content_type

    ordering_map = {
        None: "name",
        "name": "name",
        "-name": "-name",
        "id": "id",
        "-id": "-id",
    }
    if ordering not in ordering_map:
        raise HttpError(400, "Invalid ordering. Allowed: name, -name, id, -id")
    qs = (
        Tag.objects.filter(
            organization=org,
            taggeditem__content_type=ct,
            taggeditem__object_id=obj_id,
        )
        .distinct()
        .order_by(ordering_map[ordering])
    )
    return qs


@router.post(
    "/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/",
    response=list[TagOut],
    auth=JWTAuth(),
    summary="Assign tags to object",
    description=TAG_ASSIGN_DESCRIPTION,
)
def assign_tags(
    request,
    org_slug: str,
    app_label: str,
    model: str,
    obj_id: int,
    data: TagAssignment,
):
    """Assign tags by name to an object. Creates tags if missing within the organization.

    Example payload:
    ["vip", "newsletter"]
    """
    resolved = resolve_org_scoped_content_object(
        request, org_slug, app_label, model, obj_id
    )
    resolved.scope.require_write()
    org = resolved.organization
    ct = resolved.content_type
    user = resolved.scope.user

    result = assign_tags_to_object(org, ct, obj_id, data.root)
    for tag_id in result.newly_assigned_tag_ids:
        logger.info(
            "audit:tag_assign org=%s user=%s app=%s model=%s obj=%s tag_id=%s",
            org.id,
            getattr(user, "id", None),
            app_label,
            model,
            obj_id,
            tag_id,
        )

    return [TagOut.model_validate(tag) for tag in result.tags]


@router.patch(
    "/orgs/{org_slug}/tags/{tag_id}/",
    response=TagOut,
    auth=JWTAuth(),
    summary="Update tag",
    description="Rename an organization tag and regenerate its slug.",
)
def update_tag(request, org_slug: str, tag_id: int, data: TagUpdate):
    scope = resolve_org_scope(request, org_slug).require_write()
    org = scope.org
    tag = get_object_or_404(Tag, id=tag_id, organization=org)
    if data.name is not None:
        tag = rename_tag(tag, data.name)
    return TagOut.model_validate(
        {
            "id": tag.id,
            "name": tag.name,
            "slug": tag.slug,
            "organization_id": tag.organization_id,
        }
    )


@router.delete(
    "/orgs/{org_slug}/tags/{tag_id}/",
    response=DetailResponse,
    auth=JWTAuth(),
    summary="Delete tag",
    description="Delete one organization tag by id.",
)
def delete_tag(request, org_slug: str, tag_id: int):
    scope = resolve_org_scope(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    tag = get_object_or_404(Tag, id=tag_id, organization=org)
    deleted_tag_id = delete_tag_service(tag)
    logger.info(
        "audit:tag_delete org=%s user=%s tag_id=%s",
        org.id,
        getattr(user, "id", None),
        deleted_tag_id,
    )
    return DetailResponse(detail="deleted")


@router.delete(
    "/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/",
    response=RemovedCountResponse,
    auth=JWTAuth(),
    summary="Bulk unassign object tags",
    description="Remove multiple tag ids from an organization-scoped object.",
)
def unassign_tags(
    request, org_slug: str, app_label: str, model: str, obj_id: int, tag_ids: list[int]
):
    """Bulk unassign tags from an object.

    Accepts a JSON array of tag IDs. Example payload:
    [1, 4, 7]
    """
    resolved = resolve_org_scoped_content_object(
        request, org_slug, app_label, model, obj_id
    )
    resolved.scope.require_write()
    org = resolved.organization
    ct = resolved.content_type
    user = resolved.scope.user

    result = unassign_tags_from_object(
        organization=org,
        content_type=ct,
        object_id=obj_id,
        tag_ids=tag_ids,
    )
    if result.removed_count:
        logger.info(
            "audit:tag_bulk_unassign org=%s user=%s app=%s model=%s obj=%s tags=%s",
            org.id,
            getattr(user, "id", None),
            app_label,
            model,
            obj_id,
            tag_ids,
        )
    return RemovedCountResponse(removed_count=result.removed_count)


@router.delete(
    "/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/{slug}/",
    response=DetailResponse,
    auth=JWTAuth(),
    summary="Unassign object tag by slug",
    description="Remove one tag from an object by tag slug. Missing tags are treated as already removed.",
)
def unassign_tag_by_slug(
    request, org_slug: str, app_label: str, model: str, obj_id: int, slug: str
):
    """Unassign a single tag from an object by tag slug."""
    resolved = resolve_org_scoped_content_object(
        request, org_slug, app_label, model, obj_id
    )
    resolved.scope.require_write()
    org = resolved.organization
    ct = resolved.content_type
    user = resolved.scope.user

    result = unassign_tag_from_object_by_slug(
        organization=org,
        content_type=ct,
        object_id=obj_id,
        slug=slug,
    )
    if result.removed_count:
        logger.info(
            "audit:tag_unassign org=%s user=%s app=%s model=%s obj=%s tag_id=%s",
            org.id,
            getattr(user, "id", None),
            app_label,
            model,
            obj_id,
            result.tag_id,
        )
    return DetailResponse(detail="removed")
