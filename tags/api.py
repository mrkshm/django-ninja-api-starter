from ninja import Router
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

def get_tags_router():
    router = Router(tags=["tags"])

    def get_org_for_request(request, org_slug):
        user = request.user
        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            raise HttpError(404, "Organization not found")
        if not is_member(user, org):
            raise HttpError(403, "You do not have access to this organization")
        return org

    @router.get("/orgs/{org_slug}/tags/", response=list[TagOut], auth=JWTAuth())
    @paginate(LimitOffsetPagination)
    def list_tags(request, org_slug: str):
        org = get_org_for_request(request, org_slug)
        return Tag.objects.filter(organization=org).order_by("id")

    @router.post("/orgs/{org_slug}/tags/", response=TagOut, auth=JWTAuth())
    def create_tag(request, org_slug: str, data: TagCreate):
        org = get_org_for_request(request, org_slug)
        return Tag.objects.create(organization=org, **data.model_dump())

    @router.post("/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/", response=list[TagOut], auth=JWTAuth())
    def assign_tags(request, org_slug: str, app_label:str, model:str, obj_id:int, tags: list[str]):
        org = get_org_for_request(request, org_slug)
        ct = get_object_or_404(ContentType, app_label=app_label, model=model)
        Model = apps.get_model(app_label, model)
        obj = get_object_or_404(Model, pk=obj_id)
        if getattr(obj, "organization_id", None) != org.id:
            raise HttpError(403, "Object does not belong to this organization")
        out = []
        for name in tags:
            tag, _ = Tag.objects.get_or_create(organization=org, name=name, defaults={"slug": slugify(name)})
            TaggedItem.objects.get_or_create(tag=tag, content_type=ct, object_id=obj_id)
            out.append(tag)
        return [TagOut.model_validate({
            "id": tag.id,
            "name": tag.name,
            "slug": tag.slug,
            "organization_id": tag.organization_id,
        }) for tag in out]

    @router.patch("/orgs/{org_slug}/tags/{tag_id}/", response=TagOut, auth=JWTAuth())
    def update_tag(request, org_slug: str, tag_id: int, data: TagUpdate):
        org = get_org_for_request(request, org_slug)
        tag = get_object_or_404(Tag, id=tag_id, organization=org)
        if data.name:
            if Tag.objects.filter(organization=org, name=data.name).exclude(id=tag.id).exists():
                from django.http import HttpResponseBadRequest
                return HttpResponseBadRequest("A tag with this name already exists in this organization.")
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
        return {"detail": "deleted"}

    @router.delete("/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/{slug}/", auth=JWTAuth())
    def unassign_tag(request, org_slug: str, app_label:str, model:str, obj_id:int, slug:str):
        org = get_org_for_request(request, org_slug)
        ct = get_object_or_404(ContentType, app_label=app_label, model=model)
        tag = get_object_or_404(Tag, slug=slug, organization=org)
        TaggedItem.objects.filter(tag=tag, content_type=ct, object_id=obj_id).delete()
        return {"detail":"removed"}

    return router