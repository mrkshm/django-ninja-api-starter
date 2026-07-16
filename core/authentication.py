from django.utils import timezone
from ninja_jwt.authentication import JWTAuth as NinjaJWTAuth
from ninja_jwt.exceptions import AuthenticationFailed

from accounts.models import AuthSession, User


class JWTAuth(NinjaJWTAuth):
    """JWT authentication bound to an active, revocable device session."""

    def get_user(self, validated_token):
        user = cast(User, super().get_user(validated_token))

        if not user.is_active:
            raise AuthenticationFailed("User is inactive")

        if validated_token.get("auth_version") != user.auth_version:
            raise AuthenticationFailed("Session is no longer valid")

        session_id = validated_token.get("session_id")
        if not session_id:
            raise AuthenticationFailed("Token has no session")

        if not AuthSession.objects.filter(
            id=session_id,
            user=user,
            auth_version=user.auth_version,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).exists():
            raise AuthenticationFailed("Session is no longer valid")

        return user


from typing import cast
