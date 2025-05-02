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
    return user

@users_router.patch("/me", response=UserProfileOut, auth=JWTAuth())
def update_me(request, data: UserProfileUpdate):
    user = request.auth
    require_authenticated_user(user)
    for field, value in data.dict(exclude_unset=True).items():
        setattr(user, field, value)
    user.save()
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
