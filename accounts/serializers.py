from __future__ import annotations

from accounts.models import User
from accounts.schemas import UserProfileOut
from organizations.models import Organization


def serialize_user_profile(
    user: User,
    organization: Organization | None,
) -> UserProfileOut:
    return UserProfileOut(
        id=user.pk,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        slug=user.slug,
        org_name=organization.name if organization else "",
        org_slug=organization.slug if organization else "",
        location=user.location,
        about=user.about,
        avatar_path=user.avatar_path,
        notification_preferences=user.notification_preferences,
        preferred_theme=user.preferred_theme,
        preferred_language=user.preferred_language,
        finished_onboarding=user.finished_onboarding,
        email_verified=user.email_verified,
        created_at=user.created_at,
    )
