import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from ninja import Router, Status
from ninja.errors import HttpError
from ninja_jwt.schema import TokenVerifyInputSchema

from accounts.models import (
    PendingEmailChange,
    PendingRegistration,
)
from accounts.operations import (
    AccountOperationError,
)
from accounts.operations import change_password as change_password_operation
from accounts.operations import (
    confirm_email_change,
)
from accounts.operations import (
    confirm_password_reset as confirm_password_reset_operation,
)
from accounts.operations import request_email_change as request_email_change_operation
from accounts.operations import (
    rotate_password_reset,
)
from accounts.schemas import (
    ChangePasswordSchema,
    CustomTokenOutputSchema,
    DeleteAccountSchema,
    EmailSchema,
    EmailUpdateSchema,
    LogoutInputSchema,
    PasswordResetRequestSchema,
    PasswordResetSchema,
    ReauthenticationResponse,
    RegisterSchema,
    RegistrationVerificationSchema,
    TokenInputSchema,
    TokenPairInputSchema,
    TokenRefreshInputSchema,
    TokenRefreshOutputSchema,
    UnverifiedUserSchema,
)
from accounts.services import (
    authenticate_for_token,
    delete_user_account,
    issue_token_pair,
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
    token_verify_throttle,
    verification_throttle,
)
from accounts.tokens import generate_raw_token, hash_token
from accounts.validation import normalize_and_validate_email
from core.authentication import JWTAuth
from core.utils.auth_utils import get_request_user
from organizations.services import ActiveOwnerRequiredError

EMAIL_VERIFICATION_EXPIRY_HOURS = 12
EMAIL_CHANGE_TOKEN_EXPIRY_HOURS = 24
PASSWORD_RESET_TOKEN_EXPIRY_HOURS = 2
REGISTRATION_RESPONSE_DETAIL = (
    "If the address can be registered, a verification email has been sent."
)
PASSWORD_RESET_RESPONSE_DETAIL = (
    "If the email exists, a password reset link has been sent."
)

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


def send_verification_email(email: str, token: str) -> None:
    verification_link = f"{settings.FRONTEND_URL}/verify-registration#token={token}"
    try:
        send_templated_email(
            "registration_verification.txt",
            {
                "project_name": settings.PROJECT_NAME,
                "user_display_name": email,
                "verification_link": verification_link,
                "expiry_hours": EMAIL_VERIFICATION_EXPIRY_HOURS,
            },
            [email],
        )
    except Exception as exc:
        logger.warning("accounts:verification_email_failed")
        raise HttpError(500, "Failed to send verification email.") from exc


def create_pending_registration(email: str) -> None:
    if User.objects.filter(email__iexact=email).exists():
        return
    token = generate_raw_token()
    token_hash = hash_token(token)
    expires_at = timezone.now() + timedelta(hours=EMAIL_VERIFICATION_EXPIRY_HOURS)
    try:
        PendingRegistration.objects.update_or_create(
            email=email,
            defaults={"token": token_hash, "expires_at": expires_at},
        )
    except IntegrityError:
        # A concurrent registration or account creation won the race. The
        # endpoint remains intentionally generic.
        return
    try:
        send_verification_email(email, token)
    except HttpError:
        PendingRegistration.objects.filter(email=email, token=token_hash).delete()
        raise


@auth_router.post("/register/", throttle=[register_throttle])
def register(request, data: RegisterSchema):
    email = data.email
    create_pending_registration(email)

    return {"detail": REGISTRATION_RESPONSE_DETAIL}


@auth_router.post("/verify-registration")
def verify_registration(request, data: RegistrationVerificationSchema):
    error = None
    user = None
    try:
        with transaction.atomic():
            try:
                pending = PendingRegistration.objects.select_for_update().get(
                    token=hash_token(data.token)
                )
            except PendingRegistration.DoesNotExist:
                error = "Invalid or expired token."
            else:
                if pending.is_expired():
                    pending.delete()
                    error = "Token has expired."
                elif User.objects.filter(email__iexact=pending.email).exists():
                    pending.delete()
                    error = "Invalid or expired token."
                else:
                    candidate = User(email=pending.email)
                    validate_new_password(data.password, user=candidate)
                    user = User.objects.create_user(
                        email=pending.email,
                        password=data.password,
                        email_verified=True,
                    )
                    pending.delete()
    except IntegrityError as exc:
        raise HttpError(409, "Registration could not be completed.") from exc

    if error is not None or user is None:
        raise HttpError(400, error or "Invalid or expired token.")

    access, refresh = issue_token_pair(user, device_name=data.device_name or "")
    audit_logger.info("audit:registration_verified user=%s", user.pk)
    return {
        "detail": "Email verified successfully.",
        "access": access,
        "refresh": refresh,
    }


@auth_router.post("/resend-verification", throttle=[verification_throttle])
def resend_verification(request, data: EmailSchema):
    try:
        email = normalize_and_validate_email(data.email)
    except ValueError:
        return {"detail": REGISTRATION_RESPONSE_DETAIL}
    create_pending_registration(email)

    return {"detail": REGISTRATION_RESPONSE_DETAIL}


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
    try:
        delete_user_account(user)
    except ActiveOwnerRequiredError as exc:
        raise HttpError(409, str(exc)) from exc
    return {"detail": "Account deleted successfully."}


@auth_router.post(
    "/change-password/", auth=JWTAuth(), response=ReauthenticationResponse
)
def change_password(request, data: ChangePasswordSchema):
    user = get_request_user(request)
    try:
        change_password_operation(
            user_id=user.pk,
            old_password=data.old_password,
            new_password=data.new_password,
        )
    except AccountOperationError as exc:
        raise HttpError(400, str(exc)) from exc
    return ReauthenticationResponse(detail="Password changed successfully.")


@auth_router.patch("/email", auth=JWTAuth(), throttle=[email_change_throttle])
def request_email_change(request, data: EmailUpdateSchema):
    user = get_request_user(request)
    try:
        delivery = request_email_change_operation(
            user_id=user.pk,
            new_email=data.email,
            current_password=data.current_password,
            expiry_hours=EMAIL_CHANGE_TOKEN_EXPIRY_HOURS,
        )
    except AccountOperationError as exc:
        raise HttpError(400, str(exc)) from exc

    verification_link = (
        f"{settings.FRONTEND_URL}/verify-email-change#token={delivery.raw_token}"
    )
    try:
        send_templated_email(
            "email_change_requested.txt",
            {
                "project_name": settings.PROJECT_NAME,
                "user_display_name": delivery.display_name,
                "old_email": delivery.old_email,
                "new_email": delivery.new_email,
            },
            [delivery.old_email],
        )
        send_templated_email(
            "email_change_verification.txt",
            {
                "project_name": settings.PROJECT_NAME,
                "user_display_name": delivery.display_name,
                "new_email": delivery.new_email,
                "verification_link": verification_link,
            },
            [delivery.new_email],
        )
    except Exception as exc:
        PendingEmailChange.objects.filter(
            pk=delivery.pending_id,
            token=delivery.token_hash,
        ).delete()
        logger.warning(
            "accounts:email_change_verification_failed user=%s",
            delivery.user_id,
        )
        raise HttpError(500, "Failed to send verification email.") from exc
    audit_logger.info("audit:email_change_requested user=%s", delivery.user_id)
    return {"detail": "Verification email sent. Please check your new address."}


@auth_router.post("/email/verify", response=ReauthenticationResponse)
def verify_email_change(request, data: TokenInputSchema):
    try:
        result = confirm_email_change(raw_token=data.token)
    except AccountOperationError as exc:
        raise HttpError(400, str(exc)) from exc

    notification_context = {
        "project_name": settings.PROJECT_NAME,
        "old_email": result.old_email,
        "new_email": result.new_email,
    }
    for recipient in (result.old_email, result.new_email):
        try:
            send_templated_email(
                "email_change_completed.txt", notification_context, [recipient]
            )
        except Exception:
            logger.exception(
                "accounts:email_change_completion_notice_failed user=%s",
                result.user_id,
            )
    return ReauthenticationResponse(detail="Email address updated successfully.")


@auth_router.post(
    "/password-reset/request",
    throttle=[password_reset_request_throttle],
)
def request_password_reset(request, data: PasswordResetRequestSchema):
    """
    Send a reset email when the account exists; always return a generic response.
    """
    try:
        email = normalize_and_validate_email(data.email)
    except ValueError:
        return {"detail": PASSWORD_RESET_RESPONSE_DETAIL}
    delivery = rotate_password_reset(
        email=email,
        expiry_hours=PASSWORD_RESET_TOKEN_EXPIRY_HOURS,
    )
    if delivery is None:
        return {"detail": PASSWORD_RESET_RESPONSE_DETAIL}
    reset_link = f"{settings.FRONTEND_URL}/reset-password#token={delivery.raw_token}"
    try:
        send_templated_email(
            "password_reset.txt",
            {
                "project_name": settings.PROJECT_NAME,
                "user_display_name": delivery.display_name,
                "reset_link": reset_link,
            },
            [delivery.email],
        )
    except Exception:
        logger.exception(
            "accounts:password_reset_email_failed user=%s", delivery.user_id
        )
    return {"detail": PASSWORD_RESET_RESPONSE_DETAIL}


@auth_router.post(
    "/password-reset/confirm",
    response=ReauthenticationResponse,
    throttle=[password_reset_confirm_throttle],
)
def confirm_password_reset(request, data: PasswordResetSchema):
    """
    Reset password using token.
    """
    try:
        confirm_password_reset_operation(
            raw_token=data.token,
            new_password=data.new_password,
        )
    except AccountOperationError as exc:
        raise HttpError(400, str(exc)) from exc
    return ReauthenticationResponse(detail="Password has been reset successfully.")
