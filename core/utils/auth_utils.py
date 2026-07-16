from typing import cast

from django.http import HttpRequest
from ninja.errors import HttpError

from accounts.models import User


def require_authenticated_user(user: object | None) -> None:
    if user is None or not getattr(user, "is_authenticated", False):
        raise HttpError(401, "Authentication required")


def get_request_user(request: HttpRequest) -> User:
    user = getattr(request, "auth", None)
    require_authenticated_user(user)
    return cast(User, user)
