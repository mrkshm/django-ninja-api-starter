import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from ninja import File, Router, Schema, UploadedFile
from ninja.errors import HttpError

from core.authentication import JWTAuth
from core.utils.auth_utils import get_request_user
from core.utils.avatar import schedule_avatar_file_deletion
from core.utils.image import InvalidImageContent, resize_avatar_images
from core.utils.storage import delete_from_public_storage, upload_to_public_storage
from core.utils.uploads import UploadTooLarge, read_uploaded_file_bounded
from organizations.models import Organization

from .schemas import UsernameCheckResponse, UserProfileOut, UserProfileUpdate
from .throttles import username_check_throttle
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
    max_size = 10 * 1024 * 1024
    if (file.size or 0) > max_size:
        raise HttpError(400, "Avatar file too large (max 10MB)")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HttpError(400, "Invalid file type. Only images allowed.")
    try:
        img_bytes = read_uploaded_file_bounded(file, max_bytes=max_size)
    except UploadTooLarge as exc:
        raise HttpError(400, "Avatar file too large (max 10MB)") from exc

    try:
        small_bytes, large_bytes = resize_avatar_images(img_bytes)
    except InvalidImageContent as exc:
        raise HttpError(400, str(exc)) from exc

    user = get_request_user(request)
    old_avatar_path = user.avatar_path
    token = uuid.uuid4().hex
    filename = f"public/avatars/users/{token}.webp"
    large_filename = f"public/avatars/users/{token}_lg.webp"
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


@users_router.get(
    "/check_username",
    response=UsernameCheckResponse,
    auth=JWTAuth(),
    throttle=[username_check_throttle],
)
def check_username(request, username: str = ""):
    username = username.strip()
    is_valid, reason = validate_username_value(username)
    if not is_valid:
        return UsernameCheckResponse(available=False, reason=reason)
    if User.objects.filter(username__iexact=username).exists():
        return UsernameCheckResponse(available=False, reason="Username already taken.")
    return UsernameCheckResponse(available=True)
