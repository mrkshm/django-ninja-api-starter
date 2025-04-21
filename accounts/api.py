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
import secrets
from accounts.models import PendingEmailChange
from django.conf import settings
import os
from ninja.throttling import UserRateThrottle
from ninja import Schema
from django.db import transaction
from PIL import UnidentifiedImageError
from io import BytesIO
from django.core.files.base import ContentFile

EMAIL_CHANGE_TOKEN_EXPIRY_HOURS = 24

auth_router = Router()
User = get_user_model()

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

email_change_throttle = UserRateThrottle('3/h')

@auth_router.post("/register/", response=TokenPairSchema)
def register(request, data: RegisterSchema):
    # Check if user already exists
    if User.objects.filter(email=data.email).exists():
        raise HttpError(400, "User with this email already exists")
    user = User.objects.create_user(email=data.email, password=data.password)
    # Issue tokens
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }

@auth_router.post("/logout/")
def logout(request):
    # Stateless logout: client should delete tokens
    return {"detail": "Logged out successfully."}

@auth_router.delete("/delete/", auth=JWTAuth())
def delete_account(request):
    user = request.auth
    if user is None or not user.is_authenticated:
        raise HttpError(401, "Authentication required")
    user.delete()
    return {"detail": "Account deleted successfully."}

@auth_router.post("/change-password/", auth=JWTAuth())
def change_password(request, data: ChangePasswordSchema):
    user = request.auth
    if user is None or not user.is_authenticated:
        raise HttpError(401, "Authentication required")
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
        send_email(subject, new_email, body_text.strip())
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
