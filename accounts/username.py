from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import ConfigDict

from core.authentication import JWTAuth
from core.utils.auth_utils import get_request_user
from organizations.models import Organization

from .schemas import UserProfileOut
from .serializers import serialize_user_profile
from .username_validation import validate_username_value


class UsernameUpdateSchema(Schema):
    username: str
    model_config = ConfigDict(extra="forbid")


router = Router()
User = get_user_model()


@router.patch("/username", response=UserProfileOut, auth=JWTAuth())
@transaction.atomic
def update_username(request, data: UsernameUpdateSchema):
    user = get_request_user(request)
    new_username = data.username.strip()
    is_valid, reason = validate_username_value(new_username)
    if not is_valid:
        raise HttpError(400, reason or "Invalid username")
    # Case-insensitive uniqueness check
    if User.objects.filter(username__iexact=new_username).exclude(id=user.id).exists():
        raise HttpError(400, "Username already taken")
    # Optionally: Add more validation (allowed chars, length, etc.)
    # Routing slugs are stable identifiers; changing a display username must not
    # invalidate user or organization URLs.
    user.username = new_username
    try:
        with transaction.atomic():
            user.save(update_fields=["username", "updated_at"])
    except IntegrityError as exc:
        raise HttpError(409, "Username already taken") from exc
    # Update user's personal organization (via Membership with role='owner', type='personal')
    org = (
        Organization.objects.filter(creator=user, type="personal")
        .order_by("id")
        .first()
    )
    if not org:
        raise HttpError(500, "Personal organization not found for user")
    org.name = new_username
    org.save(update_fields=["name", "updated_at"])

    return serialize_user_profile(user, org)
