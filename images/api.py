from typing import List, Optional
import logging
from ninja import Router, File, UploadedFile, Schema
from ninja.errors import HttpError, ValidationError as NinjaValidationError
from ninja_jwt.authentication import JWTAuth
from django.shortcuts import get_object_or_404
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from organizations.models import Organization
from images.models import Image, PolymorphicImageRelation
from images.schemas import ImageOut, PolymorphicImageRelationOut, ImageVariants, BulkAttachOut, BulkDetachOut, ImagePatchIn
from ninja.pagination import LimitOffsetPagination, paginate
from ninja.throttling import UserRateThrottle
from django.db import transaction
from core.utils.idempotency import read_cached_response, store_cached_response, HEADER_NAME
from django.core.files.storage import default_storage
from core.utils.utils import generate_upload_filename
from core.utils.image import resize_images
from core.utils.storage import upload_to_storage
from django.utils import timezone
from django.core.files.base import ContentFile
import os
from datetime import datetime
from django.http import JsonResponse
from core.utils.auth_utils import get_org_or_404, check_object_belongs_to_org, check_contact_member
from django.conf import settings

"""
Per-user throttles (configurable via settings):
Defaults are conservative and can be overridden in Django settings, e.g.:

IMAGES_RATE_LIMIT_BULK_UPLOAD = "30/h"
IMAGES_RATE_LIMIT_BULK_DELETE = "30/h"
IMAGES_RATE_LIMIT_BULK_ATTACH = "60/h"
IMAGES_RATE_LIMIT_BULK_DETACH = "60/h"
"""

class LoggingUserRateThrottle(UserRateThrottle):
    """User rate throttle that logs when a request is throttled (429)."""
    def allow_request(self, request, view=None):
        try:
            allowed = super().allow_request(request, view)
        except TypeError:
            # Compatibility with possible 2-arg signature
            allowed = super().allow_request(request)
        if not allowed:
            user_id = getattr(getattr(request, "user", None), "id", None)
            org = None
            # Best-effort org extraction from path like /orgs/{org_slug}/...
            try:
                parts = (request.path or "").split("/")
                if "orgs" in parts:
                    idx = parts.index("orgs")
                    org = parts[idx + 1] if len(parts) > idx + 1 else None
            except Exception:
                pass
            rate = getattr(self, "rate", None)
            remote = request.META.get("REMOTE_ADDR") if hasattr(request, "META") else None
            logger.warning(
                "audit:rate_limited user=%s org=%s path=%s rate=%s ip=%s",
                user_id, org, getattr(request, "path", None), rate, remote,
            )
        return allowed

upload_throttle = LoggingUserRateThrottle(getattr(settings, "IMAGES_RATE_LIMIT_UPLOAD", "60/h"))
bulk_upload_throttle = LoggingUserRateThrottle(getattr(settings, "IMAGES_RATE_LIMIT_BULK_UPLOAD", "30/h"))
bulk_delete_throttle = LoggingUserRateThrottle(getattr(settings, "IMAGES_RATE_LIMIT_BULK_DELETE", "30/h"))
bulk_attach_throttle = LoggingUserRateThrottle(getattr(settings, "IMAGES_RATE_LIMIT_BULK_ATTACH", "60/h"))
bulk_detach_throttle = LoggingUserRateThrottle(getattr(settings, "IMAGES_RATE_LIMIT_BULK_DETACH", "60/h"))

class BulkDeleteResponse(Schema):
    id: int = None
    status: str
    error: str = None

class BulkUploadResponse(Schema):
    id: int = None
    file: str = None
    status: str
    error: Optional[str] = None

class BulkImageIdsIn(Schema):
    image_ids: List[int]

class ImageIdsIn(Schema):
    image_ids: list[int]

class ReorderIn(Schema):
    image_ids: list[int]

router = Router(tags=["images"])
logger = logging.getLogger("audit")

# Helper function to check org membership using the new permission helper
def get_org_for_request(request, org_slug):
    user = getattr(request, "auth", request.user)
    org = get_org_or_404(org_slug)
    check_contact_member(user, org)
    return org

# List all images for an organization
@router.get("/orgs/{org_slug}/images/", response=List[ImageOut], auth=JWTAuth())
@paginate(LimitOffsetPagination)
def list_images_for_org(request, org_slug: str, ordering: str | None = None):
    org = get_org_for_request(request, org_slug)
    ordering_map = {
        None: "-created_at",
        "created_at": "created_at",
        "-created_at": "-created_at",
        "title": "title",
        "-title": "-title",
    }
    if ordering not in ordering_map:
        raise HttpError(400, "Invalid ordering. Allowed: created_at, -created_at, title, -title")
    images = Image.objects.filter(organization=org).order_by(ordering_map[ordering])
    out: list[dict] = []
    for img in images:
        file_name = img.file.name if hasattr(img.file, 'name') else str(img.file)
        base, ext = os.path.splitext(file_name)
        url = default_storage.url(file_name) if file_name else None
        variants = ImageVariants(
            original=url,
            thumb=default_storage.url(f"{base}_thumb.webp"),
            sm=default_storage.url(f"{base}_sm.webp"),
            md=default_storage.url(f"{base}_md.webp"),
            lg=default_storage.url(f"{base}_lg.webp"),
        )
        out.append({
            "id": img.id,
            "file": file_name,
            "url": url,
            "variants": variants.model_dump(),
            "description": img.description,
            "alt_text": img.alt_text,
            "title": img.title,
            "organization_id": img.organization_id,
            "creator_id": img.creator_id,
            "created_at": img.created_at.isoformat() if img.created_at else None,
            "updated_at": img.updated_at.isoformat() if img.updated_at else None,
        })
    return out

# List all images for an object
@router.get("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/", response=List[PolymorphicImageRelationOut], auth=JWTAuth())
@paginate(LimitOffsetPagination)
def list_images_for_object(request, org_slug: str, app_label: str, model: str, obj_id: int, ordering: str | None = None):
    org = get_org_for_request(request, org_slug)
    ct = get_object_or_404(ContentType, app_label=app_label, model=model)
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)
    # Support ordering by relation order (default), then fallback to image fields
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
    result = []
    for rel in relations:
        file_name = rel.image.file.name if hasattr(rel.image.file, 'name') else str(rel.image.file)
        base, ext = os.path.splitext(file_name)
        url = default_storage.url(file_name) if file_name else None
        variants = ImageVariants(
            original=url,
            thumb=default_storage.url(f"{base}_thumb.webp"),
            sm=default_storage.url(f"{base}_sm.webp"),
            md=default_storage.url(f"{base}_md.webp"),
            lg=default_storage.url(f"{base}_lg.webp"),
        )
        result.append({
            "id": rel.id,
            "image": {
                "id": rel.image.id,
                "file": file_name,
                "url": url,
                "variants": variants.model_dump(),
                "created_at": rel.image.created_at.isoformat() if rel.image.created_at else None,
                "updated_at": rel.image.updated_at.isoformat() if rel.image.updated_at else None,
                "title": rel.image.title,
                "description": rel.image.description,
                "alt_text": rel.image.alt_text,
                "organization_id": rel.image.organization_id,
                "creator_id": rel.image.creator_id,
            },
            "content_type": rel.content_type.model,
            "object_id": rel.object_id,
            "is_cover": getattr(rel, "is_cover", False),
        })
    return result

# Attach images to an object
@router.post("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/", response=List[PolymorphicImageRelationOut], auth=JWTAuth())
def attach_images(request, org_slug: str, app_label: str, model: str, obj_id: int, data: ImageIdsIn):
    org = get_org_for_request(request, org_slug)
    user = request.user
    ct = get_object_or_404(ContentType, app_label=app_label, model=model)
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)
    out = []
    # Determine current ordering and primary for this object
    rel_qs = PolymorphicImageRelation.objects.filter(content_type=ct, object_id=obj_id)
    has_primary = rel_qs.filter(is_cover=True).exists()
    existing_orders = rel_qs.exclude(order__isnull=True).values_list("order", flat=True)
    next_order = (max(existing_orders) + 1) if existing_orders else 0
    for image_id in data.image_ids:
        image = get_object_or_404(Image, id=image_id, organization=org)
        rel, created = PolymorphicImageRelation.objects.get_or_create(
            image=image, content_type=ct, object_id=obj_id
        )
        if created:
            # Assign default order and primary
            if rel.order is None:
                rel.order = next_order
                next_order += 1
            if not has_primary:
                rel.is_cover = True
                has_primary = True
            rel.save(update_fields=["order", "is_cover"])  # ensure persisted
            logger.info(
                "audit:image_attach org=%s user=%s app=%s model=%s obj=%s image=%s rel=%s",
                org.id, getattr(user, "id", None), app_label, model, obj_id, image.id, rel.id,
            )
        file_name = image.file.name if hasattr(image.file, 'name') else str(image.file)
        base, ext = os.path.splitext(file_name)
        url = default_storage.url(file_name) if file_name else None
        variants = ImageVariants(
            original=url,
            thumb=default_storage.url(f"{base}_thumb.webp"),
            sm=default_storage.url(f"{base}_sm.webp"),
            md=default_storage.url(f"{base}_md.webp"),
            lg=default_storage.url(f"{base}_lg.webp"),
        )
        out.append({
            "id": rel.id,
            "image": {
                "id": image.id,
                "file": file_name,
                "url": url,
                "variants": variants.model_dump(),
                "created_at": image.created_at.isoformat() if image.created_at else None,
                "updated_at": image.updated_at.isoformat() if image.updated_at else None,
                "title": image.title,
                "description": image.description,
                "alt_text": image.alt_text,
                "organization_id": image.organization_id,
                "creator_id": image.creator_id,
            },
            "content_type": rel.content_type.model,
            "object_id": rel.object_id,
            "is_cover": getattr(rel, "is_cover", False),
        })
    return out

# Bulk attach images to an object
@router.post("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_attach/", response=BulkAttachOut, auth=JWTAuth(), throttle=[bulk_attach_throttle])
def bulk_attach_images(
    request,
    org_slug: str,
    app_label: str,
    model: str,
    obj_id: int,
    data: BulkImageIdsIn,
):
    # Idempotency check
    cached = read_cached_response(request)
    if cached:
        status, data = cached
        return (status, data) if status != 200 else data

    org = get_org_for_request(request, org_slug)
    user = request.user
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)
    requested_ids = set(data.image_ids)
    images = Image.objects.filter(id__in=requested_ids, organization=org)
    found_ids = set(images.values_list("id", flat=True))
    missing = requested_ids - found_ids
    if missing:
        # Some images do not belong to this org or do not exist
        raise HttpError(403, "One or more images do not belong to this organization")
    attached = []
    with transaction.atomic():
        ct = ContentType.objects.get_for_model(obj)
        rel_qs = PolymorphicImageRelation.objects.select_for_update().filter(content_type=ct, object_id=obj.pk)
        has_primary = rel_qs.filter(is_cover=True).exists()
        existing_orders = rel_qs.exclude(order__isnull=True).values_list("order", flat=True)
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
                rel.save(update_fields=["order", "is_cover"])  # persist defaults
                attached.append(image.id)
    if attached:
        logger.info(
            "audit:image_bulk_attach org=%s user=%s app=%s model=%s obj=%s attached=%s",
            org.id, getattr(user, "id", None), app_label, model, obj_id, attached,
        )
    resp = {"attached": attached}
    store_cached_response(request, 200, resp)
    return resp

# Reorder images for an object and set primary to the first
@router.post("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/reorder", auth=JWTAuth())
def reorder_images(request, org_slug: str, app_label: str, model: str, obj_id: int, data: ReorderIn):
    org = get_org_for_request(request, org_slug)
    user = request.user
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)
    ct = ContentType.objects.get_for_model(obj)

    rels = list(
        PolymorphicImageRelation.objects.filter(content_type=ct, object_id=obj.pk).select_related("image")
    )
    if not rels:
        return {"detail": "ok"}
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
            new_is_cover = (idx == 0)
            changed = False
            if rel.order != idx:
                rel.order = idx
                changed = True
            if rel.is_cover != new_is_cover:
                rel.is_cover = new_is_cover
                changed = True
            if changed:
                updates.append(rel)
        if updates:
            PolymorphicImageRelation.objects.bulk_update(updates, ["order", "is_cover"]) 
        logger.info(
            "audit:image_reorder org=%s user=%s app=%s model=%s obj=%s images=%s",
            org.id, getattr(user, "id", None), app_label, model, obj_id, provided,
        )
    return {"detail": "ok"}

# Bulk detach images from an object
@router.post("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_detach/", response=BulkDetachOut, auth=JWTAuth(), throttle=[bulk_detach_throttle])
def bulk_detach_images(
    request,
    org_slug: str,
    app_label: str,
    model: str,
    obj_id: int,
    data: BulkImageIdsIn,
):
    cached = read_cached_response(request)
    if cached:
        status, data = cached
        return (status, data) if status != 200 else data

    org = get_org_for_request(request, org_slug)
    user = request.user
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)
    images = Image.objects.filter(id__in=data.image_ids, organization=org)
    detached = []
    with transaction.atomic():
        for image in images:
            deleted, _ = PolymorphicImageRelation.objects.filter(
                image=image,
                content_type=ContentType.objects.get_for_model(obj),
                object_id=obj.pk,
            ).delete()
            if deleted:
                detached.append(image.id)
    if detached:
        logger.info(
            "audit:image_bulk_detach org=%s user=%s app=%s model=%s obj=%s detached=%s",
            org.id, getattr(user, "id", None), app_label, model, obj_id, detached,
        )
    resp = {"detached": detached}
    store_cached_response(request, 200, resp)
    return resp

# Remove an image from an object
@router.delete("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/{image_id}/", auth=JWTAuth(), response={204: None})
def remove_image_from_object(request, org_slug: str, app_label: str, model: str, obj_id: int, image_id: int):
    org = get_org_for_request(request, org_slug)
    user = request.user
    ct = get_object_or_404(ContentType, app_label=app_label, model=model)
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)
    rel = get_object_or_404(PolymorphicImageRelation, image_id=image_id, content_type=ct, object_id=obj_id)
    rel.delete()
    logger.info(
        "audit:image_detach org=%s user=%s app=%s model=%s obj=%s image=%s",
        org.id, getattr(user, "id", None), app_label, model, obj_id, image_id,
    )
    return 204, None

# Edit image metadata (title, description, alt_text)
@router.patch("/orgs/{org_slug}/images/{image_id}/", response={200: ImageOut, 400: dict}, auth=JWTAuth())
def edit_image_metadata(request, org_slug: str, image_id: int, data: ImagePatchIn):
    org = get_org_for_request(request, org_slug)
    image = get_object_or_404(Image, id=image_id, organization=org)
    payload = data.model_dump(exclude_unset=True)
    # Apply only known fields
    for field in ("title", "description", "alt_text"):
        if field in payload:
            setattr(image, field, payload[field])
    image.save()
    # Build response with variants
    file_name = image.file.name if hasattr(image.file, 'name') else str(image.file)
    base, ext = os.path.splitext(file_name)
    url = default_storage.url(file_name) if file_name else None
    variants = ImageVariants(
        original=url,
        thumb=default_storage.url(f"{base}_thumb.webp"),
        sm=default_storage.url(f"{base}_sm.webp"),
        md=default_storage.url(f"{base}_md.webp"),
        lg=default_storage.url(f"{base}_lg.webp"),
    )
    out = {
        "id": image.id,
        "file": file_name,
        "url": url,
        "variants": variants.model_dump(),
        "description": image.description,
        "alt_text": image.alt_text,
        "title": image.title,
        "organization_id": image.organization_id,
        "creator_id": image.creator_id,
        "created_at": image.created_at.isoformat() if image.created_at else None,
        "updated_at": image.updated_at.isoformat() if image.updated_at else None,
    }
    return ImageOut.model_validate(out)

# Upload a new image (with resizing, storing only the base filename)
@router.post("/orgs/{org_slug}/images/", response={200: ImageOut, 400: dict}, auth=JWTAuth(), throttle=[upload_throttle])
def upload_image(request, org_slug: str, file: UploadedFile = File(...)):
    org = get_org_for_request(request, org_slug)
    user = request.user
    # File validation using centralized settings
    max_bytes = getattr(settings, "UPLOAD_IMAGE_MAX_BYTES", 10 * 1024 * 1024)
    if file.size > max_bytes:
        return 400, {"detail": f"File too large. Maximum allowed size is {int(max_bytes/1024/1024)}MB."}
    prefixes = getattr(settings, "UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES", ("image/",))
    if not any(str(file.content_type or "").startswith(p) for p in prefixes):
        return 400, {"detail": "Invalid file type. Only images are allowed."}
    # Save file
    filename = generate_upload_filename(f"img_{org.slug[:8]}", file.name)
    upload_to_storage(filename, file.read())
    img = Image.objects.create(
        file=filename,
        organization=org,
        creator_id=getattr(user, "id", None),
        title=file.name,
        description="",
        alt_text=""
    )
    # Convert model to dictionary with proper types for validation
    file_name = str(img.file)
    base, ext = os.path.splitext(file_name)
    url = default_storage.url(file_name)
    variants = ImageVariants(
        original=url,
        thumb=default_storage.url(f"{base}_thumb.webp"),
        sm=default_storage.url(f"{base}_sm.webp"),
        md=default_storage.url(f"{base}_md.webp"),
        lg=default_storage.url(f"{base}_lg.webp"),
    )
    img_dict = {
        "id": img.id,
        "file": file_name,
        "url": url,
        "variants": variants.model_dump(),
        "description": img.description,
        "alt_text": img.alt_text,
        "title": img.title,
        "organization_id": img.organization_id,
        "creator_id": img.creator_id,
        "created_at": img.created_at.isoformat() if img.created_at else None,
        "updated_at": img.updated_at.isoformat() if img.updated_at else None
    }
    # Return serialized output with correct types
    return ImageOut.model_validate(img_dict)

# Bulk upload images
@router.post("/orgs/{org_slug}/bulk-upload/", response=List[BulkUploadResponse], auth=JWTAuth(), throttle=[bulk_upload_throttle])
def bulk_upload_images(request, org_slug: str):
    cached = read_cached_response(request)
    if cached:
        status, data = cached
        return (status, data) if status != 200 else data

    org = get_org_for_request(request, org_slug)
    user = request.user
    responses = []
    
    # Ensure 'files' is in the request
    files = request.FILES.getlist('files')
    if not files:
        return [BulkUploadResponse(status="error", error="No files uploaded")]
    
    with transaction.atomic():
        for file in files:
            try:
                max_bytes = getattr(settings, "UPLOAD_IMAGE_MAX_BYTES", 10 * 1024 * 1024)
                if file.size > max_bytes:
                    responses.append(BulkUploadResponse(status="error", error="File too large", file=file.name))
                    continue
                prefixes = getattr(settings, "UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES", ("image/",))
                if not any(str(file.content_type or "").startswith(p) for p in prefixes):
                    responses.append(BulkUploadResponse(status="error", error="Invalid file type", file=file.name))
                    continue
                filename = generate_upload_filename(f"img_{org.slug[:8]}", file.name)
                upload_to_storage(filename, file.read())
                img = Image.objects.create(
                    file=filename,
                    organization=org,
                    creator_id=getattr(user, "id", None),
                    title=file.name,
                    description="",
                    alt_text=""
                )
                responses.append(BulkUploadResponse(status="success", id=img.id, file=str(img.file)))
            except Exception as e:
                responses.append(BulkUploadResponse(status="error", error=str(e), file=file.name if hasattr(file, 'name') else 'unknown'))
    store_cached_response(request, 200, [r.model_dump() if hasattr(r, 'model_dump') else r for r in responses])
    return responses

# Delete an image (removes all versions from storage and all relations)
@router.delete("/orgs/{org_slug}/images/{image_id}/", auth=JWTAuth(), response={204: None})
def delete_image(request, org_slug: str, image_id: int):
    org = get_org_for_request(request, org_slug)
    image = get_object_or_404(Image, id=image_id, organization=org)
    PolymorphicImageRelation.objects.filter(image=image).delete()
    base, ext = os.path.splitext(image.file.name if hasattr(image.file, 'name') else image.file)
    for suffix in ["thumb", "sm", "md", "lg"]:
        versioned_filename = f"{base}_{suffix}.webp"
        default_storage.delete(versioned_filename)
    default_storage.delete(image.file.name if hasattr(image.file, 'name') else image.file)
    image.delete()
    logger.info(
        "audit:image_delete org=%s user=%s image=%s",
        org.id, getattr(request.user, "id", None), image_id,
    )
    return 204, None

# Bulk delete images
@router.post("/orgs/{org_slug}/bulk-delete/", response={204: None, 400: dict}, auth=JWTAuth(), throttle=[bulk_delete_throttle])
def bulk_delete_images(request, org_slug: str):
    cached = read_cached_response(request)
    if cached:
        status, data = cached
        return (status, data)

    org = get_org_for_request(request, org_slug)
    user = request.user
    
    # Parse JSON data from request body
    try:
        data = request.POST.dict() if request.POST else {}
        if not data and request.body:
            import json
            data = json.loads(request.body.decode('utf-8'))
            
        ids = data.get("ids", [])
        if not ids:
            return 400, {"detail": "No ids provided for deletion"}
        
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
        store_cached_response(request, 204, None)
        return 204, None
        
    except json.JSONDecodeError:
        return 400, {"detail": "Invalid JSON data"}
    except Exception as e:
        return 400, {"detail": str(e)}



 

# Upload image: return 400 on validation error (not 422)

def custom_validation_error(request, exc):
    # Return 400 instead of 422 for validation errors
    return JsonResponse({"detail": str(exc)}, status=400)