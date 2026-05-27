import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from ninja.errors import HttpError
from ninja_jwt.tokens import RefreshToken

from core.email_utils import render_email_template
from core.tasks import send_email_task


User = get_user_model()
logger = logging.getLogger(__name__)


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


def send_templated_email(template_name: str, context: dict, recipients: list[str]) -> None:
    subject, body_text = render_email_template(template_name, context)
    try:
        send_email_task.delay(subject, body_text, recipients)
    except Exception:
        logger.exception(
            "accounts:email_send_failed template=%s recipients=%s",
            template_name,
            recipients,
        )
        raise
