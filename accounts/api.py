from ninja import Router
from django.contrib.auth import get_user_model
from ninja_jwt.controller import NinjaJWTDefaultController
from ninja_jwt.tokens import RefreshToken
from ninja.errors import ValidationError, HttpError
from ninja_jwt.authentication import JWTAuth
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.email_utils import send_email
from core.tasks import send_email_task
import secrets
from accounts.models import PendingEmailChange, PendingPasswordReset, PendingRegistration
from django.conf import settings
import os
from ninja.throttling import UserRateThrottle
from ninja import Schema
from django.db import transaction
from PIL import UnidentifiedImageError
from io import BytesIO
from django.core.files.base import ContentFile
from core.utils.auth_utils import require_authenticated_user
from ninja_jwt.schema import TokenObtainPairInputSchema, TokenObtainPairOutputSchema

EMAIL_VERIFICATION_EXPIRY_HOURS = 12
EMAIL_CHANGE_TOKEN_EXPIRY_HOURS = 24
PASSWORD_RESET_TOKEN_EXPIRY_HOURS = 2

# Custom JWT controller that adds email verification check
from ninja_extra import api_controller, route

# Define custom schemas for responses
class UnverifiedUserSchema(Schema):
    detail: str
    email_verified: bool = False

class CustomTokenOutputSchema(Schema):
    access: str
    refresh: str
    email: str = ""  # Add the email field that seems to be required

@api_controller('/token', tags=['Auth'])
class CustomJWTController(NinjaJWTDefaultController):
    @route.post("/pair", response={200: CustomTokenOutputSchema, 403: UnverifiedUserSchema}, url_name="token_obtain_pair")
    def obtain_token(self, request, data: TokenObtainPairInputSchema):
        # First validate credentials using parent method
        try:
            # Get the user by email for validation
            user = User.objects.get(email=data.email)
            
            # Check if the password is valid
            if not user.check_password(data.password):
                raise HttpError(401, "Invalid credentials")
                
            # Check if email is verified
            if not user.email_verified:
                return 403, UnverifiedUserSchema(
                    detail="Please verify your email address before logging in.",
                    email_verified=False
                )
            
            # Email is verified, generate tokens
            refresh = RefreshToken.for_user(user)
            return CustomTokenOutputSchema(
                access=str(refresh.access_token),
                refresh=str(refresh),
                email=user.email  # Include the email field
            )
                
        except User.DoesNotExist:
            raise HttpError(401, "Invalid credentials")

auth_router = Router()
User = get_user_model()

def send_verification_email(user, token):
    display_name = f"{user.first_name} {user.last_name}".strip() or user.email
    
    with open(os.path.join(settings.BASE_DIR, "core/email_templates/registration_verification.txt")) as f:
        template = f.read()
        
    verification_link = f"{settings.FRONTEND_URL}/api/v1/auth/verify-registration?token={token}"
    
    body = template.replace("{{ project_name }}", settings.PROJECT_NAME)
    body = body.replace("{{ user_display_name }}", display_name)
    body = body.replace("{{ verification_link }}", verification_link)
    
    # Email subject is first line
    subject, body_text = body.split("\n", 1)
    subject = subject.replace("Subject: ", "").strip()
    
    try:
        send_email_task.delay(subject, body_text.strip(), [user.email])
    except Exception as e:
        raise HttpError(500, f"Failed to send verification email: {str(e)}")

class RegisterSchema(Schema):
    email: str
    password: str

class TokenPairSchema(Schema):
    access: str
    refresh: str

class ChangePasswordSchema(Schema):
    old_password: str
    new_password: str

class EmailUpdateSchema(Schema):
    email: str

class EmailSchema(Schema):
    email: str

class PasswordResetRequestSchema(Schema):
    email: str

class PasswordResetSchema(Schema):
    token: str
    new_password: str

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
    except ValidationError:
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
    # Prepare and send email
    display_name = f"{user.first_name} {user.last_name}".strip() or user.email
    with open(os.path.join(settings.BASE_DIR, "core/email_templates/email_change_verification.txt")) as f:
        template = f.read()
    verification_link = f"{settings.FRONTEND_URL}/verify-email-change?token={token}"
    body = template.replace("{{ project_name }}", settings.PROJECT_NAME)
    body = body.replace("{{ user_display_name }}", display_name)
    body = body.replace("{{ new_email }}", new_email)
    body = body.replace("{{ verification_link }}", verification_link)
    # Email subject is first line
    subject, body_text = body.split("\n", 1)
    subject = subject.replace("Subject: ", "").strip()
    try:
        send_email_task.delay(subject, body_text.strip(), [new_email])
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
    except ValidationError:
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
    with open(os.path.join(settings.BASE_DIR, "core/email_templates/password_reset.txt")) as f:
        template = f.read()
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    body = template.replace("{{ project_name }}", settings.PROJECT_NAME)
    body = body.replace("{{ user_display_name }}", display_name)
    body = body.replace("{{ reset_link }}", reset_link)
    subject, body_text = body.split("\n", 1)
    subject = subject.replace("Subject: ", "").strip()
    try:
        send_email_task.delay(subject, body_text.strip(), [user.email])
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
