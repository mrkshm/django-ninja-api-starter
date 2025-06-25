from ninja import Router
import logging
from django.shortcuts import get_object_or_404
from tags.models import Tag, TaggedItem
from tags.schemas import TagCreate, TagOut, TagUpdate
from django.contrib.contenttypes.models import ContentType
from django.utils.text import slugify
from django.apps import apps
from organizations.models import Organization
from organizations.permissions import is_member
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth
from ninja.pagination import LimitOffsetPagination, paginate
from core.utils.auth_utils import check_object_belongs_to_org, get_org_or_404, check_contact_member

# Module-level router and logger
router = Router(tags=["tags"])
logger = logging.getLogger("audit")

def get_org_for_request(request, org_slug):
    user = request.user
    org = get_org_or_404(org_slug)
    check_contact_member(user, org)
    return org

@router.get("/orgs/{org_slug}/tags/", response=list[TagOut], auth=JWTAuth())
@paginate(LimitOffsetPagination)
def list_tags(request, org_slug: str, ordering: str | None = None):
    org = get_org_for_request(request, org_slug)
    ordering_map = {
        None: "name",
        "name": "name",
        "-name": "-name",
        "id": "id",
        "-id": "-id",
    }
    if ordering not in ordering_map:
        raise HttpError(400, "Invalid ordering. Allowed: name, -name, id, -id")
    return Tag.objects.filter(organization=org).order_by(ordering_map[ordering])

@router.get("/orgs/{org_slug}/tags/search/", response=list[TagOut], auth=JWTAuth())
@paginate(LimitOffsetPagination)
def search_tags(request, org_slug: str, q: str = None):
    """
    Search for tags in an organization by name.
    """
    org = get_org_for_request(request, org_slug)
    queryset = Tag.objects.filter(organization=org)
    if q:
        queryset = queryset.filter(name__icontains=q)
    return queryset.order_by("name")

@router.get("/orgs/{org_slug}/tags/by-slug/{slug}/", response=TagOut, auth=JWTAuth())
def get_tag_by_slug(request, org_slug: str, slug: str):
    org = get_org_for_request(request, org_slug)
    tag = get_object_or_404(Tag, slug=slug, organization=org)
    return TagOut.model_validate(tag)

@router.post("/orgs/{org_slug}/tags/", response=TagOut, auth=JWTAuth())
def create_tag(request, org_slug: str, data: TagCreate):
    org = get_org_for_request(request, org_slug)
    name = data.name
    if Tag.objects.filter(organization=org, name=name).exists():
        raise HttpError(400, "A tag with this name already exists in this organization.")
    tag = Tag.objects.create(organization=org, name=name, slug=slugify(name))
    logger.info(
        "audit:tag_create org=%s user=%s tag_id=%s name=%s",
        org.id, getattr(request.user, "id", None), tag.id, tag.name,
    )
    return tag

@router.get("/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/", response=list[TagOut], auth=JWTAuth())
@paginate(LimitOffsetPagination)
def list_tags_for_object(request, org_slug: str, app_label: str, model: str, obj_id: int, ordering: str | None = None):
    """List tags for a specific object (paginated)."""
    org = get_org_for_request(request, org_slug)
    ct = get_object_or_404(ContentType, app_label=app_label, model=model)
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)

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

@router.post("/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/", response=list[TagOut], auth=JWTAuth())
def assign_tags(request, org_slug: str, app_label: str, model: str, obj_id: int, data: list[str]):
    """Assign tags by name to an object. Creates tags if missing within the organization.

    Example payload:
    ["vip", "newsletter"]
    """
    org = get_org_for_request(request, org_slug)
    ct = get_object_or_404(ContentType, app_label=app_label, model=model)
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)

    out: list[Tag] = []
    for name in data:
        slug = slugify(name)
        tag, _created = Tag.objects.get_or_create(organization=org, slug=slug, defaults={"name": name})
        # Ensure name stays in sync with slug if the tag existed but had different casing
        if tag.name != name and not _created:
            tag.name = name
            tag.save(update_fields=["name"])
        ti, created = TaggedItem.objects.get_or_create(tag=tag, content_type=ct, object_id=obj_id)
        if created:
            logger.info(
                "audit:tag_assign org=%s user=%s app=%s model=%s obj=%s tag_id=%s",
                org.id, getattr(request.user, "id", None), app_label, model, obj_id, tag.id,
            )
        out.append(tag)

    return [TagOut.model_validate(tag) for tag in out]

@router.patch("/orgs/{org_slug}/tags/{tag_id}/", response=TagOut, auth=JWTAuth())
def update_tag(request, org_slug: str, tag_id: int, data: TagUpdate):
    org = get_org_for_request(request, org_slug)
    tag = get_object_or_404(Tag, id=tag_id, organization=org)
    if data.name:
        if Tag.objects.filter(organization=org, name=data.name).exclude(id=tag.id).exists():
            # normalized via global HttpError handler to {"detail": str}
            raise HttpError(400, "A tag with this name already exists in this organization.")
        tag.name = data.name
        tag.slug = slugify(data.name)
    tag.save()
    return TagOut.model_validate({
        "id": tag.id,
        "name": tag.name,
        "slug": tag.slug,
        "organization_id": tag.organization_id,
    })

@router.delete("/orgs/{org_slug}/tags/{tag_id}/", auth=JWTAuth())
def delete_tag(request, org_slug: str, tag_id: int):
    org = get_org_for_request(request, org_slug)
    tag = get_object_or_404(Tag, id=tag_id, organization=org)
    tag.delete()
    logger.info(
        "audit:tag_delete org=%s user=%s tag_id=%s",
        org.id, getattr(request.user, "id", None), tag_id,
    )
    return {"detail": "deleted"}

@router.delete("/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/", auth=JWTAuth())
def unassign_tags(request, org_slug: str, app_label: str, model: str, obj_id: int, tag_ids: list[int]):
    """Bulk unassign tags from an object.

    Accepts a JSON array of tag IDs. Example payload:
    [1, 4, 7]
    """
    org = get_org_for_request(request, org_slug)
    ct = get_object_or_404(ContentType, app_label=app_label, model=model)
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)

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
            org.id, getattr(request.user, "id", None), app_label, model, obj_id, tag_ids,
        )
    return {"removed_count": deleted}

@router.delete("/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/{slug}/", auth=JWTAuth())
def unassign_tag_by_slug(request, org_slug: str, app_label: str, model: str, obj_id: int, slug: str):
    """Unassign a single tag from an object by tag slug."""
    org = get_org_for_request(request, org_slug)
    ct = get_object_or_404(ContentType, app_label=app_label, model=model)
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)

    try:
        tag = Tag.objects.get(organization=org, slug=slug)
    except Tag.DoesNotExist:
        # If tag doesn't exist in org, treat as already unassigned
        return {"detail": "removed"}
    deleted, _ = TaggedItem.objects.filter(tag=tag, content_type=ct, object_id=obj_id).delete()
    if deleted:
        logger.info(
            "audit:tag_unassign org=%s user=%s app=%s model=%s obj=%s tag_id=%s",
            org.id, getattr(request.user, "id", None), app_label, model, obj_id, tag.id,
        )
    return {"detail": "removed"}

# Back-compat factory and exports
def get_tags_router():
    return router

tags_router = router