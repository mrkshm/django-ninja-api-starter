from ninja import Router, Schema, File, UploadedFile
from ninja.errors import HttpError
from core.authentication import JWTAuth
from django.db import transaction
from core.utils import (
    generate_presigned_storage_url,
    generate_upload_filename,
    resize_avatar_images,
    delete_existing_avatar,
    upload_to_storage
)
from core.utils.auth_utils import get_request_user
from PIL import Image, UnidentifiedImageError
from io import BytesIO
import os
from .schemas import UserProfileOut, UserProfileUpdate, UsernameCheckResponse
from django.contrib.auth import get_user_model
from .username import router as username_router
from .username_validation import validate_username_value
from organizations.models import Organization
from botocore.exceptions import ClientError

User = get_user_model()

# You can add more user/profile endpoints here as needed
users_router = Router()

users_router.add_router("/",username_router, tags=["users"])

class AvatarUploadResponse(Schema):
    avatar_url: str
    avatar_large_url: str


def attach_personal_org_fields(user):
    org = (
        Organization.objects
        .filter(
            memberships__user=user,
            memberships__role="owner",
            type="personal",
        )
        .order_by("id")
        .first()
    )
    user.org_name = org.name if org else ""
    user.org_slug = org.slug if org else ""
    return user


@users_router.post("/avatar", response=AvatarUploadResponse, auth=JWTAuth())
def upload_avatar(request, file: UploadedFile = File(...)):
    """
    Handles avatar upload: validates, deletes old, resizes, uploads, updates DB.
    """
    if file.file is not None:
        file.file.seek(0)
    img_bytes = file.read()
    
    if (file.size or 0) > 10 * 1024 * 1024:
        raise HttpError(400, "Avatar file too large (max 10MB)")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HttpError(400, "Invalid file type. Only images allowed.")

    try:
        img = Image.open(BytesIO(img_bytes))
        img.verify()  # This will raise if not a valid image
    except (UnidentifiedImageError, Exception):
        raise HttpError(400, "Uploaded file is not a valid image.")

    user = get_request_user(request)
    with transaction.atomic():
        delete_existing_avatar(user)
        # Always use .webp extension for resized avatars
        filename = generate_upload_filename('avatar', file.name or "avatar", ext='.webp')
        base, ext = os.path.splitext(filename)
        large_filename = f"{base}_lg{ext}"
        small_bytes, large_bytes = resize_avatar_images(img_bytes)
        small_avatar_url = upload_to_storage(filename, small_bytes)
        large_avatar_url = upload_to_storage(large_filename, large_bytes)
        user.avatar_path = filename
        user.save()
    return AvatarUploadResponse(avatar_url=small_avatar_url, avatar_large_url=large_avatar_url)

@users_router.delete("/avatar", auth=JWTAuth())
def delete_avatar(request):
    user = get_request_user(request)
    # Use helper to delete from storage
    delete_existing_avatar(user)
    # Remove avatar reference from profile
    user.avatar_path = None
    user.save()
    return {"detail": "Avatar deleted."}

@users_router.get("/me", response=UserProfileOut, auth=JWTAuth())
def get_me(request):
    user = get_request_user(request)
    return attach_personal_org_fields(user)

@users_router.patch("/me", response=UserProfileOut, auth=JWTAuth())
def update_me(request, data: UserProfileUpdate):
    user = get_request_user(request)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    user.save()
    return attach_personal_org_fields(user)

@users_router.get("/check_username", response=UsernameCheckResponse)
def check_username(request, username: str = ""):
    username = username.strip()
    is_valid, reason = validate_username_value(username)
    if not is_valid:
        return UsernameCheckResponse(available=False, reason=reason)
    if User.objects.filter(username__iexact=username).exists():
        return UsernameCheckResponse(available=False, reason="Username already taken.")
    return UsernameCheckResponse(available=True)

@users_router.get("/avatars/{path:path}", auth=JWTAuth())
def get_avatar_url(request, path: str):
    """
    Generate a presigned URL for an avatar image.
    For large version, append '_lg' before the file extension.
    Example: /api/v1/avatars/avatar-user123-20240529.webp
             /api/v1/avatars/avatar-user123-20240529_lg.webp
    """
    # Validate path to prevent directory traversal
    if '..' in path or path.startswith('/'):
        raise HttpError(400, "Invalid path")
    
    # Get the base filename without extension
    base, ext = os.path.splitext(path)
    
    # Check if requesting large version
    is_large = base.endswith('_lg')
    if is_large:
        base = base[:-3]  # Remove _lg suffix
    
    # Validate filename format (example: avatar-{id}-{timestamp}-{random}.webp)
    if not (base.startswith('avatar-') and ext.lower() == '.webp'):
        raise HttpError(400, "Invalid avatar filename format")
    
    try:
        presigned_url = generate_presigned_storage_url(
            path,
            expires_in=3600,
            content_type="image/webp",
            cache_control="public, max-age=3600",
        )
        return {"url": presigned_url}
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        if error_code == 'NoSuchKey':
            raise HttpError(404, "Avatar not found")
        raise HttpError(500, f"S3 error: {error_code} - {str(e)}")
    except Exception as e:
        raise HttpError(500, f"Error generating URL: {str(e)}")
