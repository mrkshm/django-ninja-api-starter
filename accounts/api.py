import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils import timezone
from ninja import Router, Status
from ninja.errors import HttpError
from ninja.throttling import UserRateThrottle
from ninja_extra import api_controller, route
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.controller import NinjaJWTDefaultController
from ninja_jwt.tokens import RefreshToken
from ninja_jwt.schema import TokenObtainPairInputSchema

from accounts.models import PendingEmailChange, PendingPasswordReset, PendingRegistration
from accounts.schemas import (
    ChangePasswordSchema,
    CustomTokenOutputSchema,
    EmailSchema,
    EmailUpdateSchema,
    PasswordResetRequestSchema,
    PasswordResetSchema,
    RegisterSchema,
    UnverifiedUserSchema,
)
from accounts.services import authenticate_for_token, issue_token_pair
from core.email_utils import render_email_template
from core.tasks import send_email_task
from core.utils.auth_utils import require_authenticated_user

EMAIL_VERIFICATION_EXPIRY_HOURS = 12
EMAIL_CHANGE_TOKEN_EXPIRY_HOURS = 24
PASSWORD_RESET_TOKEN_EXPIRY_HOURS = 2

@api_controller('/token', tags=['Auth'])
class CustomJWTController(NinjaJWTDefaultController):
    @route.post("/pair", response={200: CustomTokenOutputSchema, 403: UnverifiedUserSchema}, url_name="token_obtain_pair")
    def obtain_token(self, request, data: TokenObtainPairInputSchema):
        user, is_verified = authenticate_for_token(data.email, data.password)
        if not is_verified:
            return Status(
                403,
                UnverifiedUserSchema(
                    detail="Please verify your email address before logging in.",
                    email_verified=False,
                ),
            )

        access, refresh = issue_token_pair(user)
        return CustomTokenOutputSchema(access=access, refresh=refresh, email=user.email)

auth_router = Router()
User = get_user_model()

def send_verification_email(user, token):
    display_name = f"{user.first_name} {user.last_name}".strip() or user.email
    verification_link = f"{settings.FRONTEND_URL}/api/v1/auth/verify-registration?token={token}"
    subject, body_text = render_email_template(
        "registration_verification.txt",
        {
            "project_name": settings.PROJECT_NAME,
            "user_display_name": display_name,
            "verification_link": verification_link,
        },
    )
    
    try:
        send_email_task.delay(subject, body_text, [user.email])
    except Exception as e:
        raise HttpError(500, f"Failed to send verification email: {str(e)}")

email_change_throttle = UserRateThrottle('3/h')
password_reset_throttle = UserRateThrottle('3/h')

@auth_router.post("/register/")
def register(request, data: RegisterSchema):
    # Check if user already exists
    if User.objects.filter(email=data.email).exists():
        raise HttpError(400, "User with this email already exists")
    
    # Create user with email_verified=False
    user = User.objects.create_user(
        email=data.email, 
        password=data.password,
        email_verified=False
    )
    
    # Generate token and expiry
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timezone.timedelta(hours=EMAIL_VERIFICATION_EXPIRY_HOURS)
    
    # Create pending registration
    PendingRegistration.objects.create(
        user=user, 
        token=token, 
        expires_at=expires_at
    )
    
    # Send verification email
    send_verification_email(user, token)
    
    return {"detail": "Registration successful. Please check your email to verify your account."}

@auth_router.get("/verify-registration")
def verify_registration(request, token: str):
    try:
        pending = PendingRegistration.objects.get(token=token)
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
    refresh = RefreshToken.for_user(user)
    return {
        "detail": "Email verified successfully.",
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }

@auth_router.post("/resend-verification")
def resend_verification(request, data: EmailSchema):
    email = data.email.strip().lower()
    
    try:
        user = User.objects.get(email=email, email_verified=False)
    except User.DoesNotExist:
        # Don't reveal if user exists
        return {"detail": "If your account exists and is not verified, a new verification email has been sent."}
    
    # Remove existing pending registration
    PendingRegistration.objects.filter(user=user).delete()
    
    # Create new token
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timezone.timedelta(hours=EMAIL_VERIFICATION_EXPIRY_HOURS)
    
    PendingRegistration.objects.create(
        user=user, 
        token=token, 
        expires_at=expires_at
    )
    
    send_verification_email(user, token)
    
    return {"detail": "If your account exists and is not verified, a new verification email has been sent."}
    
@auth_router.post("/logout/")
def logout(request):
    # Stateless logout: client should delete tokens
    return {"detail": "Logged out successfully."}

@auth_router.delete("/delete/", auth=JWTAuth())
def delete_account(request):
    user = request.auth
    require_authenticated_user(user)
    user.delete()
    return {"detail": "Account deleted successfully."}

@auth_router.post("/change-password/", auth=JWTAuth())
def change_password(request, data: ChangePasswordSchema):
    user = request.auth
    require_authenticated_user(user)
    if not user.check_password(data.old_password):
        raise HttpError(400, "Old password is incorrect")
    user.set_password(data.new_password)
    user.save()
    return {"detail": "Password changed successfully."}

@auth_router.patch("/email", auth=JWTAuth(), throttle=[email_change_throttle])
def request_email_change(request, data: EmailUpdateSchema):
    """
    Initiate email change: send verification email to new address.
    """
    user = request.auth
    require_authenticated_user(user)
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
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timezone.timedelta(hours=EMAIL_CHANGE_TOKEN_EXPIRY_HOURS)
    PendingEmailChange.objects.create(user=user, new_email=new_email, token=token, expires_at=expires_at)
    display_name = f"{user.first_name} {user.last_name}".strip() or user.email
    verification_link = f"{settings.FRONTEND_URL}/verify-email-change?token={token}"
    subject, body_text = render_email_template(
        "email_change_verification.txt",
        {
            "project_name": settings.PROJECT_NAME,
            "user_display_name": display_name,
            "new_email": new_email,
            "verification_link": verification_link,
        },
    )
    try:
        send_email_task.delay(subject, body_text, [new_email])
    except Exception as e:
        raise HttpError(500, f"Failed to send verification email: {str(e)}")
    return {"detail": "Verification email sent. Please check your new address."}

@auth_router.get("/email/verify")
def verify_email_change(request, token: str):
    """
    Verify email change using token.
    """
    try:
        pending = PendingEmailChange.objects.get(token=token)
    except PendingEmailChange.DoesNotExist:
        raise HttpError(400, "Invalid or expired token.")
    if pending.is_expired():
        pending.delete()
        raise HttpError(400, "Token has expired.")
    # Check uniqueness again (race condition safety)
    if User.objects.filter(email__iexact=pending.new_email).exclude(id=pending.user.id).exists():
        pending.delete()
        raise HttpError(400, "Email already taken.")
    pending.user.email = pending.new_email
    pending.user.save()
    pending.delete()
    return {"detail": "Email address updated successfully."}

@auth_router.post("/password-reset/request", throttle=[password_reset_throttle])
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
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timezone.timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRY_HOURS)
    PendingPasswordReset.objects.create(user=user, token=token, expires_at=expires_at)
    display_name = f"{user.first_name} {user.last_name}".strip() or user.email
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    subject, body_text = render_email_template(
        "password_reset.txt",
        {
            "project_name": settings.PROJECT_NAME,
            "user_display_name": display_name,
            "reset_link": reset_link,
        },
    )
    try:
        send_email_task.delay(subject, body_text, [user.email])
    except Exception:
        pass  # Don't leak info
    return {"detail": "If the email exists, a password reset link has been sent."}

@auth_router.post("/password-reset/confirm")
def confirm_password_reset(request, data: PasswordResetSchema):
    """
    Reset password using token.
    """
    token = data.token
    new_password = data.new_password
    try:
        pending = PendingPasswordReset.objects.get(token=token)
    except PendingPasswordReset.DoesNotExist:
        raise HttpError(400, "Invalid or expired token.")
    if pending.is_expired():
        pending.delete()
        raise HttpError(400, "Token has expired.")
    user = pending.user
    user.set_password(new_password)
    user.save()
    pending.delete()
    return {"detail": "Password has been reset successfully."}
