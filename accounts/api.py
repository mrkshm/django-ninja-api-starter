import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
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
    LogoutInputSchema,
    PasswordResetRequestSchema,
    PasswordResetSchema,
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
    token_verify_throttle,
    verification_throttle,
)
from accounts.tokens import generate_raw_token, hash_token
from core.authentication import JWTAuth
from core.utils.auth_utils import get_request_user
from organizations.services import ActiveOwnerRequiredError

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
    email = normalize_email(data.email)
    try:
        validate_email(email)
    except DjangoValidationError as exc:
        raise HttpError(400, "Invalid email address") from exc
    create_pending_registration(email)

    return {
        "detail": "If the address can be registered, a verification email has been sent."
    }


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
        email = normalize_email(data.email)
        validate_email(email)
    except DjangoValidationError:
        return {
            "detail": "If the address can be registered, a verification email has been sent."
        }
    create_pending_registration(email)

    return {
        "detail": "If the address can be registered, a verification email has been sent."
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
    try:
        delete_user_account(user)
    except ActiveOwnerRequiredError as exc:
        raise HttpError(409, str(exc)) from exc
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
    user = get_request_user(request)
    new_email = normalize_email(data.email)
    try:
        validate_email(new_email)
    except DjangoValidationError as exc:
        raise HttpError(400, "Invalid email address") from exc
    if new_email == normalize_email(user.email):
        raise HttpError(400, "New email must differ from the current email.")
    if User.objects.filter(email__iexact=new_email).exclude(id=user.id).exists():
        raise HttpError(400, "Email already taken")

    token = generate_raw_token()
    token_hash = hash_token(token)
    expires_at = timezone.now() + timedelta(hours=EMAIL_CHANGE_TOKEN_EXPIRY_HOURS)
    with transaction.atomic():
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        if not locked_user.check_password(data.current_password):
            raise HttpError(400, "Password is incorrect")
        pending, _ = PendingEmailChange.objects.update_or_create(
            user=locked_user,
            defaults={
                "new_email": new_email,
                "token": token_hash,
                "expires_at": expires_at,
                "auth_version": locked_user.auth_version,
            },
        )

    old_email = locked_user.email
    display_name = (
        f"{locked_user.first_name} {locked_user.last_name}".strip() or old_email
    )
    verification_link = f"{settings.FRONTEND_URL}/verify-email-change#token={token}"
    try:
        send_templated_email(
            "email_change_requested.txt",
            {
                "project_name": settings.PROJECT_NAME,
                "user_display_name": display_name,
                "old_email": old_email,
                "new_email": new_email,
            },
            [old_email],
        )
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
        PendingEmailChange.objects.filter(pk=pending.pk, token=token_hash).delete()
        logger.warning(
            "accounts:email_change_verification_failed user=%s",
            locked_user.pk,
        )
        raise HttpError(500, "Failed to send verification email.") from exc
    audit_logger.info("audit:email_change_requested user=%s", locked_user.pk)
    return {"detail": "Verification email sent. Please check your new address."}


@auth_router.post("/email/verify")
def verify_email_change(request, data: TokenInputSchema):
    error = None
    old_email = None
    new_email = None
    changed_user = None
    try:
        with transaction.atomic():
            try:
                pending = PendingEmailChange.objects.select_for_update().get(
                    token=hash_token(data.token)
                )
            except PendingEmailChange.DoesNotExist:
                error = "Invalid or expired token."
            else:
                changed_user = User.objects.select_for_update().get(pk=pending.user_id)
                if pending.is_expired():
                    pending.delete()
                    error = "Token has expired."
                elif pending.auth_version != changed_user.auth_version:
                    pending.delete()
                    error = "Invalid or expired token."
                elif (
                    User.objects.filter(email__iexact=pending.new_email)
                    .exclude(id=changed_user.id)
                    .exists()
                ):
                    pending.delete()
                    error = "Email already taken."
                else:
                    old_email = changed_user.email
                    new_email = pending.new_email
                    changed_user.email = new_email
                    changed_user.save(update_fields=["email", "updated_at"])
                    revoke_all_sessions(changed_user)
                    pending.delete()
    except IntegrityError as exc:
        raise HttpError(400, "Email already taken.") from exc

    if error is not None or changed_user is None or not old_email or not new_email:
        raise HttpError(400, error or "Invalid or expired token.")

    notification_context = {
        "project_name": settings.PROJECT_NAME,
        "old_email": old_email,
        "new_email": new_email,
    }
    for recipient in (old_email, new_email):
        try:
            send_templated_email(
                "email_change_completed.txt", notification_context, [recipient]
            )
        except Exception:
            logger.exception(
                "accounts:email_change_completion_notice_failed user=%s",
                changed_user.pk,
            )
    audit_logger.info("audit:email_change_completed user=%s", changed_user.pk)
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
