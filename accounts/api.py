import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.db import IntegrityError, transaction
from ninja import Router, Status
from ninja.errors import HttpError
from ninja_jwt.schema import TokenVerifyInputSchema

from accounts.models import (
    PendingEmailChange,
    PendingPasswordReset,
    PendingRegistration,
)
from accounts.schemas import (
    ChangePasswordSchema,
    CustomTokenOutputSchema,
    DeleteAccountSchema,
    EmailSchema,
    EmailUpdateSchema,
    PasswordResetRequestSchema,
    PasswordResetSchema,
    RegisterSchema,
    LogoutInputSchema,
    TokenRefreshInputSchema,
    TokenRefreshOutputSchema,
    TokenPairInputSchema,
    TokenInputSchema,
    UnverifiedUserSchema,
)
from accounts.services import (
    authenticate_for_token,
    delete_user_account,
    issue_token_pair,
    normalize_email,
    revoke_all_sessions,
    revoke_session_from_refresh,
    rotate_token_pair,
    send_templated_email,
    validate_new_password,
)
from accounts.throttles import (
    email_change_throttle,
    login_throttle,
    logout_throttle,
    password_reset_confirm_throttle,
    password_reset_request_throttle,
    refresh_throttle,
    register_throttle,
    verification_throttle,
    token_verify_throttle,
)
from accounts.tokens import generate_raw_token, hash_token
from core.authentication import JWTAuth
from core.utils.auth_utils import get_request_user

EMAIL_VERIFICATION_EXPIRY_HOURS = 12
EMAIL_CHANGE_TOKEN_EXPIRY_HOURS = 24
PASSWORD_RESET_TOKEN_EXPIRY_HOURS = 2

token_router = Router(tags=["token"])
auth_router = Router()
User = get_user_model()
logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


@token_router.post(
    "/pair",
    response={200: CustomTokenOutputSchema, 403: UnverifiedUserSchema},
    throttle=[login_throttle],
)
def obtain_token_pair(request, data: TokenPairInputSchema):
    try:
        user, is_verified = authenticate_for_token(data.email, data.password)
    except HttpError:
        audit_logger.warning(
            "audit:login_failed ip=%s",
            request.META.get("REMOTE_ADDR"),
        )
        raise
    if not is_verified:
        return Status(
            403,
            UnverifiedUserSchema(
                detail="Please verify your email address before logging in.",
                email_verified=False,
            ),
        )

    access, refresh = issue_token_pair(user, device_name=data.device_name or "")
    audit_logger.info("audit:login_succeeded user=%s", user.pk)
    return CustomTokenOutputSchema(access=access, refresh=refresh, email=user.email)


@token_router.post(
    "/refresh",
    response={200: TokenRefreshOutputSchema},
    throttle=[refresh_throttle],
)
def refresh_token(request, data: TokenRefreshInputSchema):
    access, refresh = rotate_token_pair(data.refresh)
    return TokenRefreshOutputSchema(access=access, refresh=refresh)


@token_router.post(
    "/verify",
    response={200: TokenVerifyInputSchema.get_response_schema()},
    throttle=[token_verify_throttle],
)
def verify_token(request, data: TokenVerifyInputSchema):
    return data.to_response_schema()


def send_verification_email(user, token):
    display_name = f"{user.first_name} {user.last_name}".strip() or user.email
    verification_link = f"{settings.FRONTEND_URL}/verify-registration#token={token}"
    try:
        send_templated_email(
            "registration_verification.txt",
            {
                "project_name": settings.PROJECT_NAME,
                "user_display_name": display_name,
                "verification_link": verification_link,
            },
            [user.email],
        )
    except Exception as exc:
        logger.warning(
            "accounts:verification_email_failed user=%s", getattr(user, "id", None)
        )
        raise HttpError(500, "Failed to send verification email.") from exc


@auth_router.post("/register/", throttle=[register_throttle])
def register(request, data: RegisterSchema):
    email = normalize_email(data.email)
    try:
        validate_email(email)
    except DjangoValidationError as exc:
        raise HttpError(400, "Invalid email address") from exc
    validate_new_password(data.password)
    # Check if user already exists
    if User.objects.filter(email__iexact=email).exists():
        raise HttpError(400, "User with this email already exists")

    token = generate_raw_token()
    expires_at = timezone.now() + timedelta(hours=EMAIL_VERIFICATION_EXPIRY_HOURS)
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email=email,
                password=data.password,
                email_verified=False,
            )
            PendingRegistration.objects.create(
                user=user,
                token=hash_token(token),
                expires_at=expires_at,
            )
    except IntegrityError as exc:
        raise HttpError(400, "User with this email already exists") from exc

    # Send verification email
    send_verification_email(user, token)

    return {
        "detail": "Registration successful. Please check your email to verify your account."
    }


@auth_router.post("/verify-registration")
def verify_registration(request, data: TokenInputSchema):
    token = data.token
    try:
        pending = PendingRegistration.objects.get(token=hash_token(token))
    except PendingRegistration.DoesNotExist:
        raise HttpError(400, "Invalid or expired token.")

    if pending.is_expired():
        pending.delete()
        raise HttpError(400, "Token has expired.")

    user = pending.user
    user.email_verified = True
    user.save()

    pending.delete()

    # Issue tokens
    access, refresh = issue_token_pair(user)
    return {
        "detail": "Email verified successfully.",
        "access": access,
        "refresh": refresh,
    }


@auth_router.post("/resend-verification", throttle=[verification_throttle])
def resend_verification(request, data: EmailSchema):
    email = data.email.strip().lower()

    try:
        user = User.objects.get(email=email, email_verified=False)
    except User.DoesNotExist:
        # Don't reveal if user exists
        return {
            "detail": "If your account exists and is not verified, a new verification email has been sent."
        }

    # Remove existing pending registration
    PendingRegistration.objects.filter(user=user).delete()

    # Create new token
    token = generate_raw_token()
    expires_at = timezone.now() + timedelta(hours=EMAIL_VERIFICATION_EXPIRY_HOURS)

    PendingRegistration.objects.create(
        user=user, token=hash_token(token), expires_at=expires_at
    )

    send_verification_email(user, token)

    return {
        "detail": "If your account exists and is not verified, a new verification email has been sent."
    }


@auth_router.post("/logout/", throttle=[logout_throttle])
def logout(request, data: LogoutInputSchema):
    revoke_session_from_refresh(data.refresh)
    audit_logger.info("audit:session_logged_out")
    return {"detail": "Logged out successfully."}


@auth_router.delete("/delete/", auth=JWTAuth())
def delete_account(request, data: DeleteAccountSchema):
    user = get_request_user(request)
    if not user.check_password(data.password):
        raise HttpError(400, "Password is incorrect")
    delete_user_account(user)
    return {"detail": "Account deleted successfully."}


@auth_router.post("/change-password/", auth=JWTAuth())
def change_password(request, data: ChangePasswordSchema):
    user = get_request_user(request)
    if not user.check_password(data.old_password):
        raise HttpError(400, "Old password is incorrect")
    validate_new_password(data.new_password, user=user)
    user.set_password(data.new_password)
    user.save()
    revoke_all_sessions(user)
    audit_logger.info("audit:password_changed user=%s", user.pk)
    return {"detail": "Password changed successfully."}


@auth_router.patch("/email", auth=JWTAuth(), throttle=[email_change_throttle])
def request_email_change(request, data: EmailUpdateSchema):
    """
    Initiate email change: send verification email to new address.
    """
    user = get_request_user(request)
    new_email = data.email.strip().lower()
    # Validate email format
    try:
        validate_email(new_email)
    except DjangoValidationError:
        raise HttpError(400, "Invalid email address")
    # Uniqueness check (case-insensitive)
    if User.objects.filter(email__iexact=new_email).exclude(id=user.id).exists():
        raise HttpError(400, "Email already taken")
    # Remove any previous pending changes for this user
    PendingEmailChange.objects.filter(user=user).delete()
    # Generate token and expiry
    token = generate_raw_token()
    expires_at = timezone.now() + timedelta(hours=EMAIL_CHANGE_TOKEN_EXPIRY_HOURS)
    PendingEmailChange.objects.create(
        user=user, new_email=new_email, token=hash_token(token), expires_at=expires_at
    )
    display_name = f"{user.first_name} {user.last_name}".strip() or user.email
    verification_link = f"{settings.FRONTEND_URL}/verify-email-change#token={token}"
    try:
        send_templated_email(
            "email_change_verification.txt",
            {
                "project_name": settings.PROJECT_NAME,
                "user_display_name": display_name,
                "new_email": new_email,
                "verification_link": verification_link,
            },
            [new_email],
        )
    except Exception as exc:
        logger.warning(
            "accounts:email_change_verification_failed user=%s",
            getattr(user, "id", None),
        )
        raise HttpError(500, "Failed to send verification email.") from exc
    return {"detail": "Verification email sent. Please check your new address."}


@auth_router.post("/email/verify")
def verify_email_change(request, data: TokenInputSchema):
    """
    Verify email change using token.
    """
    try:
        pending = PendingEmailChange.objects.get(token=hash_token(data.token))
    except PendingEmailChange.DoesNotExist:
        raise HttpError(400, "Invalid or expired token.")
    if pending.is_expired():
        pending.delete()
        raise HttpError(400, "Token has expired.")
    # Check uniqueness again (race condition safety)
    if (
        User.objects.filter(email__iexact=pending.new_email)
        .exclude(id=pending.user.id)
        .exists()
    ):
        pending.delete()
        raise HttpError(400, "Email already taken.")
    pending.user.email = pending.new_email
    pending.user.save()
    revoke_all_sessions(pending.user)
    pending.delete()
    return {"detail": "Email address updated successfully."}


@auth_router.post(
    "/password-reset/request",
    throttle=[password_reset_request_throttle],
)
def request_password_reset(request, data: PasswordResetRequestSchema):
    """
    Initiate password reset: send reset email if user exists (always return generic response).
    """
    email = data.email.strip().lower()
    try:
        validate_email(email)
    except DjangoValidationError:
        # Always return generic response
        return {"detail": "If the email exists, a password reset link has been sent."}
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        return {"detail": "If the email exists, a password reset link has been sent."}
    # Remove any previous pending resets for this user
    PendingPasswordReset.objects.filter(user=user).delete()
    token = generate_raw_token()
    expires_at = timezone.now() + timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRY_HOURS)
    PendingPasswordReset.objects.create(
        user=user, token=hash_token(token), expires_at=expires_at
    )
    display_name = f"{user.first_name} {user.last_name}".strip() or user.email
    reset_link = f"{settings.FRONTEND_URL}/reset-password#token={token}"
    try:
        send_templated_email(
            "password_reset.txt",
            {
                "project_name": settings.PROJECT_NAME,
                "user_display_name": display_name,
                "reset_link": reset_link,
            },
            [user.email],
        )
    except Exception:
        logger.exception("accounts:password_reset_email_failed user=%s", user.pk)
    return {"detail": "If the email exists, a password reset link has been sent."}


@auth_router.post(
    "/password-reset/confirm",
    throttle=[password_reset_confirm_throttle],
)
def confirm_password_reset(request, data: PasswordResetSchema):
    """
    Reset password using token.
    """
    token = data.token
    new_password = data.new_password
    try:
        pending = PendingPasswordReset.objects.get(token=hash_token(token))
    except PendingPasswordReset.DoesNotExist:
        raise HttpError(400, "Invalid or expired token.")
    if pending.is_expired():
        pending.delete()
        raise HttpError(400, "Token has expired.")
    user = pending.user
    validate_new_password(new_password, user=user)
    user.set_password(new_password)
    user.save()
    revoke_all_sessions(user)
    pending.delete()
    audit_logger.info("audit:password_reset_completed user=%s", user.pk)
    return {"detail": "Password has been reset successfully."}
