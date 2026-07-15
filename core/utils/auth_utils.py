from ninja.errors import HttpError


def require_authenticated_user(user):
    if user is None or not getattr(user, "is_authenticated", False):
        raise HttpError(401, "Authentication required")


def get_request_user(request):
    user = getattr(request, "auth", None)
    require_authenticated_user(user)
    return user
