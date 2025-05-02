from typing import List, Optional
from ninja import Router, File, UploadedFile, Schema
from ninja.errors import HttpError, ValidationError as NinjaValidationError
from ninja_jwt.authentication import JWTAuth
from django.shortcuts import get_object_or_404
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from organizations.models import Organization
from images.models import Image, PolymorphicImageRelation
from images.schemas import ImageOut, PolymorphicImageRelationOut
from ninja.pagination import LimitOffsetPagination, paginate
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

router = Router(tags=["images"])

# Helper function to check org membership using the new permission helper
def get_org_for_request(request, org_slug):
    user = request.user
    org = get_org_or_404(org_slug)
    check_contact_member(user, org)
    return org

# List all images for an organization
@router.get("/orgs/{org_slug}/images/", response=List[ImageOut], auth=JWTAuth())
@paginate(LimitOffsetPagination)
def list_images_for_org(request, org_slug: str):
    org = get_org_for_request(request, org_slug)
    qs = Image.objects.filter(organization=org).order_by("-created_at").values(
        "id", "file", "description", "alt_text", "title", "organization_id", "creator_id", "created_at", "updated_at"
    )
    qs_list = list(qs)
    for item in qs_list:
        for field in ("created_at", "updated_at"):
            if isinstance(item[field], datetime):
                item[field] = item[field].isoformat()
    return qs_list

# List all images for an object
@router.get("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/", response=List[PolymorphicImageRelationOut], auth=JWTAuth())
@paginate(LimitOffsetPagination)
def list_images_for_object(request, org_slug: str, app_label: str, model: str, obj_id: int):
    org = get_org_for_request(request, org_slug)
    ct = get_object_or_404(ContentType, app_label=app_label, model=model)
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)
    relations = PolymorphicImageRelation.objects.filter(content_type=ct, object_id=obj_id).select_related("image")
    result = []
    for rel in relations:
        result.append({
            "id": rel.id,
            "image": {
                "id": rel.image.id,
                "file": rel.image.file.url if rel.image.file else None,
                "created_at": rel.image.created_at.isoformat() if rel.image.created_at else None,
                "updated_at": rel.image.updated_at.isoformat() if rel.image.updated_at else None,
                "title": rel.image.title,
                "description": rel.image.description,
                "alt_text": rel.image.alt_text,
                "organization_id": rel.image.organization_id,
                "creator": rel.image.creator_id,
            },
            "content_type": rel.content_type.model,
            "object_id": rel.object_id,
            "is_cover": getattr(rel, "is_cover", False),
        })
    return result

# Attach images to an object
@router.post("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/", auth=JWTAuth())
def attach_images(request, org_slug: str, app_label: str, model: str, obj_id: int, data: ImageIdsIn):
    org = get_org_for_request(request, org_slug)
    ct = get_object_or_404(ContentType, app_label=app_label, model=model)
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)
    out = []
    for image_id in data.image_ids:
        image = get_object_or_404(Image, id=image_id, organization=org)
        rel, _ = PolymorphicImageRelation.objects.get_or_create(
            image=image, content_type=ct, object_id=obj_id
        )
        out.append({
            "id": rel.id,
            "image": {
                "id": rel.image.id,
                "file": rel.image.file.url if rel.image.file else None,
                "created_at": rel.image.created_at.isoformat() if rel.image.created_at else None,
                "updated_at": rel.image.updated_at.isoformat() if rel.image.updated_at else None,
                "title": rel.image.title,
                "description": rel.image.description,
                "alt_text": rel.image.alt_text,
                "organization_id": rel.image.organization_id,
                "creator": rel.image.creator_id,
            },
            "content_type": rel.content_type.model,
            "object_id": rel.object_id,
            "is_cover": getattr(rel, "is_cover", False),
        })
    return out

# Remove an image from an object
@router.delete("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/{image_id}/", auth=JWTAuth())
def remove_image_from_object(request, org_slug: str, app_label: str, model: str, obj_id: int, image_id: int):
    org = get_org_for_request(request, org_slug)
    ct = get_object_or_404(ContentType, app_label=app_label, model=model)
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)
    rel = get_object_or_404(PolymorphicImageRelation, image_id=image_id, content_type=ct, object_id=obj_id)
    rel.delete()
    return {"detail": "removed"}

# Edit image metadata (title, description, etc.)
@router.patch("/orgs/{org_slug}/images/{image_id}/", auth=JWTAuth())
def edit_image_metadata(request, org_slug: str, image_id: int, data: dict):
    org = get_org_for_request(request, org_slug)
    image = get_object_or_404(Image, id=image_id, organization=org)
    # TODO: validate and update fields from data
    for field, value in data.items():
        if hasattr(image, field):
            setattr(image, field, value)
    image.save()
    return {"detail": "updated"}

# Upload a new image (with resizing, storing only the base filename)
@router.post("/orgs/{org_slug}/images/", response={200: ImageOut, 400: dict}, auth=JWTAuth())
def upload_image(request, org_slug: str, file: UploadedFile = File(...)):
    org = get_org_for_request(request, org_slug)
    user = request.user
    # File validation: max size 10MB
    MAX_SIZE = 10 * 1024 * 1024
    if file.size > MAX_SIZE:
        return 400, {"detail": "File too large. Maximum allowed size is 10MB."}
    if not file.content_type.startswith("image/"):
        return 400, {"detail": "Invalid file type. Only images are allowed."}
    # Save file
    filename = generate_upload_filename(f"img_{org.slug[:8]}", file.name)
    upload_to_storage(filename, file.read())
    img = Image.objects.create(
        file=filename,
        organization=org,
        creator=user,
        title=file.name,
        description="",
        alt_text=""
    )
    # Convert model to dictionary with proper types for validation
    img_dict = {
        "id": img.id,
        "file": str(img.file),
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
@router.post("/orgs/{org_slug}/bulk-upload/", response=List[BulkUploadResponse], auth=JWTAuth())
def bulk_upload_images(request, org_slug: str):
    org = get_org_for_request(request, org_slug)
    user = request.user
    responses = []
    
    # Ensure 'files' is in the request
    files = request.FILES.getlist('files')
    if not files:
        return [BulkUploadResponse(status="error", error="No files uploaded")]
    
    for file in files:
        try:
            if file.size > 10 * 1024 * 1024:
                responses.append(BulkUploadResponse(status="error", error="File too large", file=file.name))
                continue
            if not file.content_type.startswith("image/"):
                responses.append(BulkUploadResponse(status="error", error="Invalid file type", file=file.name))
                continue
            filename = generate_upload_filename(f"img_{org.slug[:8]}", file.name)
            upload_to_storage(filename, file.read())
            img = Image.objects.create(
                file=filename,
                organization=org,
                creator=user,
                title=file.name,
                description="",
                alt_text=""
            )
            responses.append(BulkUploadResponse(status="success", id=img.id, file=str(img.file)))
        except Exception as e:
            responses.append(BulkUploadResponse(status="error", error=str(e), file=file.name if hasattr(file, 'name') else 'unknown'))
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
    return 204, None

# Bulk delete images
@router.post("/orgs/{org_slug}/bulk-delete/", response={204: None, 400: dict}, auth=JWTAuth())
def bulk_delete_images(request, org_slug: str):
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
        
        for img_id in ids:
            try:
                image = Image.objects.get(id=img_id, organization=org)
                image.delete()
            except Exception:
                continue
        return 204, None
        
    except json.JSONDecodeError:
        return 400, {"detail": "Invalid JSON data"}
    except Exception as e:
        return 400, {"detail": str(e)}

# Attach image to object
@router.post("/orgs/{org_slug}/attach/", response={200: dict, 400: dict, 403: dict, 404: dict}, auth=JWTAuth())
def attach_image(request, org_slug: str):
    org = get_org_for_request(request, org_slug)
    
    # Parse JSON data from request body
    try:
        data = request.POST.dict() if request.POST else {}
        if not data and request.body:
            import json
            data = json.loads(request.body.decode('utf-8'))
        
        # Validate required fields
        required_fields = ["image_id", "app_label", "model", "object_id"]
        for field in required_fields:
            if field not in data:
                return 400, {"detail": f"Missing required field: {field}"}
        
        image = get_object_or_404(Image, id=data["image_id"], organization=org)
        ct = get_object_or_404(ContentType, app_label=data["app_label"], model=data["model"])
        Model = apps.get_model(data["app_label"], data["model"])
        obj = get_object_or_404(Model, pk=data["object_id"])
        
        # Check organization ownership
        check_object_belongs_to_org(obj, org)
        
        # Create relation
        rel, created = PolymorphicImageRelation.objects.get_or_create(
            image=image, content_type=ct, object_id=data["object_id"]
        )
        
        return {"detail": "attached", "created": created}
    
    except Image.DoesNotExist:
        return 404, {"detail": "Image not found"}
    except ContentType.DoesNotExist:
        return 404, {"detail": "Content type not found"}
    except json.JSONDecodeError:
        return 400, {"detail": "Invalid JSON data"}
    except Exception as e:
        return 400, {"detail": str(e)}

# Detach image from object
@router.post("/orgs/{org_slug}/detach/", response={204: None, 400: dict, 403: dict, 404: dict}, auth=JWTAuth())
def detach_image(request, org_slug: str):
    org = get_org_for_request(request, org_slug)
    
    # Parse JSON data from request body
    try:
        data = request.POST.dict() if request.POST else {}
        if not data and request.body:
            import json
            data = json.loads(request.body.decode('utf-8'))
        
        # Validate required fields
        required_fields = ["image_id", "app_label", "model", "object_id"]
        for field in required_fields:
            if field not in data:
                return 400, {"detail": f"Missing required field: {field}"}
        
        image = get_object_or_404(Image, id=data["image_id"], organization=org)
        ct = get_object_or_404(ContentType, app_label=data["app_label"], model=data["model"])
        Model = apps.get_model(data["app_label"], data["model"])
        obj = get_object_or_404(Model, pk=data["object_id"])
        
        # Check organization ownership
        check_object_belongs_to_org(obj, org)
        
        deleted, _ = PolymorphicImageRelation.objects.filter(
            image=image, content_type=ct, object_id=data["object_id"]
        ).delete()
        
        return 204, None
    
    except Image.DoesNotExist:
        return 404, {"detail": "Image not found"}
    except ContentType.DoesNotExist:
        return 404, {"detail": "Content type not found"}
    except json.JSONDecodeError:
        return 400, {"detail": "Invalid JSON data"}
    except Exception as e:
        return 400, {"detail": str(e)}

# Bulk attach images to an object
@router.post("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_attach/", auth=JWTAuth())
def bulk_attach_images(
    request,
    org_slug: str,
    app_label: str,
    model: str,
    obj_id: int,
    data: BulkImageIdsIn,
):
    org = get_org_for_request(request, org_slug)
    user = request.user
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)
    images = Image.objects.filter(id__in=data.image_ids, organization=org)
    attached = []
    for image in images:
        rel, created = PolymorphicImageRelation.objects.get_or_create(
            image=image,
            content_type=ContentType.objects.get_for_model(obj),
            object_id=obj.pk,
        )
        if created:
            attached.append(image.id)
    return {"attached": attached}

# Bulk detach images from an object
@router.post("/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_detach/", auth=JWTAuth())
def bulk_detach_images(
    request,
    org_slug: str,
    app_label: str,
    model: str,
    obj_id: int,
    data: BulkImageIdsIn,
):
    org = get_org_for_request(request, org_slug)
    user = request.user
    Model = apps.get_model(app_label, model)
    obj = get_object_or_404(Model, pk=obj_id)
    check_object_belongs_to_org(obj, org)
    images = Image.objects.filter(id__in=data.image_ids, organization=org)
    detached = []
    for image in images:
        deleted, _ = PolymorphicImageRelation.objects.filter(
            image=image,
            content_type=ContentType.objects.get_for_model(obj),
            object_id=obj.pk,
        ).delete()
        if deleted:
            detached.append(image.id)
    return {"detached": detached}

# Upload image: return 400 on validation error (not 422)
from ninja.errors import ValidationError as NinjaValidationError
from django.http import JsonResponse

def custom_validation_error(request, exc):
    # Return 400 instead of 422 for validation errors
    return JsonResponse({"detail": str(exc)}, status=400)