from ninja import Router
import logging
from django.shortcuts import get_object_or_404
from tags.models import Tag, TaggedItem
from tags.schemas import (
    DetailResponse,
    RemovedCountResponse,
    TagCreate,
    TagOut,
    TagUpdate,
)
from django.utils.text import slugify
from ninja.errors import HttpError
from core.authentication import JWTAuth
from ninja.pagination import LimitOffsetPagination, paginate
from core.utils.polymorphic import resolve_org_scoped_content_object
from organizations.scope import resolve_org_scope
from tags.services import create_tag as create_tag_service, rename_tag

# Module-level router and logger
router = Router(tags=["tags"])
logger = logging.getLogger("audit")

TAG_ASSIGN_DESCRIPTION = "Assign tag names to an organization-scoped object. Missing tags are created in that organization."
TAG_OBJECT_DESCRIPTION = "Manage tags attached to a polymorphic object identified by app label, model name, and object id."


def get_org_scope_for_request(request, org_slug):
    return resolve_org_scope(request, org_slug)


@router.get(
    "/orgs/{org_slug}/tags/",
    response=list[TagOut],
    auth=JWTAuth(),
    summary="List organization tags",
    description="Return the paginated tag list for an organization. Supports ordering by name or id.",
)
@paginate(LimitOffsetPagination)
def list_tags(request, org_slug: str, ordering: str | None = None):
    scope = get_org_scope_for_request(request, org_slug)
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
    scope = get_org_scope_for_request(request, org_slug)
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
    scope = get_org_scope_for_request(request, org_slug)
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
    scope = get_org_scope_for_request(request, org_slug).require_write()
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
    request, org_slug: str, app_label: str, model: str, obj_id: int, data: list[str]
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

    out: list[Tag] = []
    for name in data:
        slug = slugify(name)
        tag, _created = Tag.objects.get_or_create(
            organization=org, slug=slug, defaults={"name": name}
        )
        # Ensure name stays in sync with slug if the tag existed but had different casing
        if tag.name != name and not _created:
            tag.name = name
            tag.save(update_fields=["name"])
        ti, created = TaggedItem.objects.get_or_create(
            tag=tag, content_type=ct, object_id=obj_id
        )
        if created:
            logger.info(
                "audit:tag_assign org=%s user=%s app=%s model=%s obj=%s tag_id=%s",
                org.id,
                getattr(user, "id", None),
                app_label,
                model,
                obj_id,
                tag.id,
            )
        out.append(tag)

    return [TagOut.model_validate(tag) for tag in out]


@router.patch(
    "/orgs/{org_slug}/tags/{tag_id}/",
    response=TagOut,
    auth=JWTAuth(),
    summary="Update tag",
    description="Rename an organization tag and regenerate its slug.",
)
def update_tag(request, org_slug: str, tag_id: int, data: TagUpdate):
    scope = get_org_scope_for_request(request, org_slug).require_write()
    org = scope.org
    tag = get_object_or_404(Tag, id=tag_id, organization=org)
    if data.name:
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
    scope = get_org_scope_for_request(request, org_slug).require_write()
    org = scope.org
    user = scope.user
    tag = get_object_or_404(Tag, id=tag_id, organization=org)
    tag.delete()
    logger.info(
        "audit:tag_delete org=%s user=%s tag_id=%s",
        org.id,
        getattr(user, "id", None),
        tag_id,
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

    qs = TaggedItem.objects.filter(
        tag_id__in=tag_ids,
        tag__organization=org,
        content_type=ct,
        object_id=obj_id,
    )
    deleted, _ = qs.delete()
    if deleted:
        logger.info(
            "audit:tag_bulk_unassign org=%s user=%s app=%s model=%s obj=%s tags=%s",
            org.id,
            getattr(user, "id", None),
            app_label,
            model,
            obj_id,
            tag_ids,
        )
    return RemovedCountResponse(removed_count=deleted)


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

    try:
        tag = Tag.objects.get(organization=org, slug=slug)
    except Tag.DoesNotExist:
        # If tag doesn't exist in org, treat as already unassigned
        return DetailResponse(detail="removed")
    deleted, _ = TaggedItem.objects.filter(
        tag=tag, content_type=ct, object_id=obj_id
    ).delete()
    if deleted:
        logger.info(
            "audit:tag_unassign org=%s user=%s app=%s model=%s obj=%s tag_id=%s",
            org.id,
            getattr(user, "id", None),
            app_label,
            model,
            obj_id,
            tag.id,
        )
    return DetailResponse(detail="removed")


# Back-compat factory and exports
def get_tags_router():
    return router


tags_router = router
