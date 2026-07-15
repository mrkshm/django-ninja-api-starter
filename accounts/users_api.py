import os
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from ninja import File, Router, Schema, UploadedFile
from ninja.errors import HttpError

from core.authentication import JWTAuth
from core.utils import resize_avatar_images
from core.utils.auth_utils import get_request_user
from core.utils.avatar import schedule_avatar_file_deletion
from core.utils.image import InvalidImageContent, validate_image_content
from core.utils.storage import (
    delete_from_public_storage,
    public_storage_url,
    upload_to_public_storage,
)
from organizations.models import Organization

from .schemas import UsernameCheckResponse, UserProfileOut, UserProfileUpdate
from .username import router as username_router
from .username_validation import validate_username_value

User = get_user_model()

# You can add more user/profile endpoints here as needed
users_router = Router()

users_router.add_router("/", username_router, tags=["users"])


class AvatarUploadResponse(Schema):
    avatar_url: str
    avatar_large_url: str


def attach_personal_org_fields(user):
    org = (
        Organization.objects.filter(
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
        validate_image_content(img_bytes)
    except InvalidImageContent as exc:
        raise HttpError(400, str(exc)) from exc

    user = get_request_user(request)
    old_avatar_path = user.avatar_path
    token = uuid.uuid4().hex
    filename = f"public/avatars/users/{token}.webp"
    large_filename = f"public/avatars/users/{token}_lg.webp"
    small_bytes, large_bytes = resize_avatar_images(img_bytes)
    uploaded: list[str] = []
    try:
        small_avatar_url = upload_to_public_storage(filename, small_bytes)
        uploaded.append(filename)
        large_avatar_url = upload_to_public_storage(large_filename, large_bytes)
        uploaded.append(large_filename)
        with transaction.atomic():
            user.avatar_path = filename
            user.save(update_fields=["avatar_path", "updated_at"])
            if old_avatar_path:
                schedule_avatar_file_deletion(old_avatar_path)
    except Exception as exc:
        for key in uploaded:
            delete_from_public_storage(key)
        raise HttpError(503, "Avatar upload is temporarily unavailable.") from exc
    return AvatarUploadResponse(
        avatar_url=small_avatar_url, avatar_large_url=large_avatar_url
    )


@users_router.delete("/avatar", auth=JWTAuth())
def delete_avatar(request):
    user = get_request_user(request)
    old_avatar_path = user.avatar_path
    with transaction.atomic():
        user.avatar_path = None
        user.save(update_fields=["avatar_path", "updated_at"])
        if old_avatar_path:
            schedule_avatar_file_deletion(old_avatar_path)
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


@users_router.get("/avatars/{path:path}", auth=None)
def get_avatar_url(request, path: str):
    """
    Generate a presigned URL for an avatar image.
    For large version, append '_lg' before the file extension.
    Example: /api/v1/avatars/avatar-user123-20240529.webp
             /api/v1/avatars/avatar-user123-20240529_lg.webp
    """
    # Validate path to prevent directory traversal
    if ".." in path or path.startswith("/"):
        raise HttpError(400, "Invalid path")

    # Get the base filename without extension
    base, ext = os.path.splitext(path)

    # Check if requesting large version
    is_large = base.endswith("_lg")
    if is_large:
        base = base[:-3]  # Remove _lg suffix

    if not (base.startswith("public/avatars/users/") and ext.lower() == ".webp"):
        raise HttpError(400, "Invalid avatar filename format")
    return {"url": public_storage_url(path)}
