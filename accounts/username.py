from ninja import Router, Schema
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth
from pydantic import ConfigDict
from django.db import transaction
from django.contrib.auth import get_user_model
from organizations.models import Organization
from core.utils import make_it_unique
from core.utils.auth_utils import get_request_user
from django.utils.text import slugify
from .schemas import UserProfileOut
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
    # Update user
    user.username = new_username  # Save as entered, but normalized for spaces
    # Regenerate slug using make_it_unique
    base_slug = slugify(new_username)
    user.slug = make_it_unique(base_slug, User, "slug")
    user.save()
    # Update user's personal organization (via Membership with role='owner', type='personal')
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
    if not org:
        raise HttpError(500, "Personal organization not found for user")
    org.name = new_username
    org.slug = user.slug
    org.save()
    
    # Add org info to user object for response
    user.org_name = org.name
    user.org_slug = org.slug
    return user
