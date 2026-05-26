from django.conf import settings
from django.contrib.auth import get_user_model
from ninja.errors import HttpError
from ninja_jwt.tokens import RefreshToken


User = get_user_model()


def authenticate_for_token(email: str, password: str):
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        raise HttpError(401, "Invalid credentials")

    if hasattr(password, "get_secret_value"):
        password = password.get_secret_value()

    if not user.check_password(password):
        raise HttpError(401, "Invalid credentials")

    require_verification = getattr(settings, "REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN", True)
    return user, not (require_verification and not user.email_verified)


def issue_token_pair(user) -> tuple[str, str]:
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)
