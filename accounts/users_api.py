from ninja import Router, Schema, File, UploadedFile
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth
from django.db import transaction
from core.utils import (
    generate_upload_filename,
    resize_avatar_images,
    delete_existing_avatar,
    upload_to_storage
)
from core.utils.auth_utils import require_authenticated_user
from PIL import Image, UnidentifiedImageError
from io import BytesIO
import os
from .schemas import UserProfileOut, UserProfileUpdate, UsernameCheckResponse
from django.contrib.auth import get_user_model
from .username import router as username_router
from organizations.models import Organization

User = get_user_model()

# You can add more user/profile endpoints here as needed
users_router = Router()

users_router.add_router("/",username_router, tags=["users"])

class AvatarUploadResponse(Schema):
    avatar_url: str
    avatar_large_url: str

@users_router.post("/avatar", response=AvatarUploadResponse, auth=JWTAuth())
def upload_avatar(request, file: UploadedFile = File(...)):
    """
    Handles avatar upload: validates, deletes old, resizes, uploads, updates DB.
    """
    print("file.size:", file.size)
    print("file.content_type:", file.content_type)
    file.file.seek(0)
    img_bytes = file.read()
    print("img_bytes length:", len(img_bytes))
    
    if file.size > 10 * 1024 * 1024:
        raise HttpError(400, "Avatar file too large (max 10MB)")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HttpError(400, "Invalid file type. Only images allowed.")

    try:
        img = Image.open(BytesIO(img_bytes))
        img.verify()  # This will raise if not a valid image
    except (UnidentifiedImageError, Exception):
        raise HttpError(400, "Uploaded file is not a valid image.")

    user = request.auth
    with transaction.atomic():
        delete_existing_avatar(user)
        # Always use .webp extension for resized avatars
        filename = generate_upload_filename('avatar', file.name, ext='.webp')
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
    user = request.auth
    require_authenticated_user(user)
    # Use helper to delete from storage
    delete_existing_avatar(user)
    # Remove avatar reference from profile
    user.avatar_path = None
    user.save()
    return {"detail": "Avatar deleted."}

@users_router.get("/me", response=UserProfileOut, auth=JWTAuth())
def get_me(request):
    user = request.auth
    require_authenticated_user(user)
    # Get user's personal organization
    org = (
        Organization.objects
        .filter(
            memberships__user=user,
            memberships__role="owner",
            type="personal"
        )
        .order_by('id')
        .first()
    )
    # Add org info to user object for response
    user.org_name = org.name if org else ""
    user.org_slug = org.slug if org else ""
    return user

@users_router.patch("/me", response=UserProfileOut, auth=JWTAuth())
def update_me(request, data: UserProfileUpdate):
    user = request.auth
    require_authenticated_user(user)
    for field, value in data.dict(exclude_unset=True).items():
        setattr(user, field, value)
    user.save()
    # Get user's personal organization
    org = (
        Organization.objects
        .filter(
            memberships__user=user,
            memberships__role="owner",
            type="personal"
        )
        .order_by('id')
        .first()
    )
    # Add org info to user object for response
    user.org_name = org.name if org else ""
    user.org_slug = org.slug if org else ""
    return user

@users_router.get("/check_username", response=UsernameCheckResponse)
def check_username(request, username: str = ""):
    # Length check
    if not username or len(username) > 50:
        return UsernameCheckResponse(available=False, reason="Username must be 1-50 characters.")
    # Uniqueness check (case-insensitive)
    from django.contrib.auth import get_user_model
    User = get_user_model()
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
    import os
    from urllib.parse import urlparse
    import boto3
    from django.conf import settings
    from ninja.errors import HttpError

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
    
    # Construct the S3 key - use the path directly as it's already the full key
    s3_key = path
    
    # Generate presigned URL
    s3_client = boto3.client(
        's3',
        endpoint_url=settings.STORAGES['default']['OPTIONS']['endpoint_url'],
        aws_access_key_id=settings.STORAGES['default']['OPTIONS']['access_key'],
        aws_secret_access_key=settings.STORAGES['default']['OPTIONS']['secret_key'],
        region_name=settings.STORAGES['default']['OPTIONS']['region_name'],
        config=boto3.session.Config(signature_version='s3v4')
    )
    
    try:
        # Generate presigned URL (expires in 1 hour)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.STORAGES['default']['OPTIONS']['bucket_name'],
                'Key': s3_key,
                'ResponseContentType': 'image/webp',
                'ResponseCacheControl': 'public, max-age=3600'  # Cache for 1 hour
            },
            ExpiresIn=3600  # 1 hour
        )
        
        return {"url": presigned_url}
        
    except s3_client.exceptions.NoSuchKey:
        raise HttpError(404, "Avatar not found")
    except s3_client.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        if error_code == 'NoSuchKey':
            raise HttpError(404, "Avatar not found")
        else:
            raise HttpError(500, f"S3 error: {error_code} - {str(e)}")
    except Exception as e:
        raise HttpError(500, f"Error generating URL: {str(e)}")