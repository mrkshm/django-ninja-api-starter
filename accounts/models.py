from __future__ import annotations

import string
import uuid

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import IntegrityError, models, transaction
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.text import slugify

from core.utils.identifiers import make_it_unique


class UserManager(BaseUserManager["User"]):
    def _clean_username(self, username):
        # Allow only alphanumerics, dots, and underscores
        allowed = set(string.ascii_letters + string.digits + "._")
        return "".join(c for c in username if c in allowed)

    def _generate_username(self, email):
        base_username = self._clean_username(email.split("@")[0])
        return make_it_unique(base_username, self.model, "username")

    def _generate_slug(self, username):
        base_slug = slugify(username)
        return make_it_unique(base_slug, self.model, "slug")

    def _retry_username(self, email, attempt):
        base = self._clean_username(email.split("@")[0]) or "user"
        suffix = uuid.uuid4().hex[:8]
        return f"{base[: 50 - len(suffix) - 1]}_{suffix}"

    def _retry_slug(self, username):
        base = slugify(username) or "user"
        suffix = uuid.uuid4().hex[:8]
        return f"{base[: 50 - len(suffix) - 1]}-{suffix}"

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email).strip().lower()
        supplied_username = extra_fields.get("username")
        supplied_slug = extra_fields.get("slug")
        for attempt in range(5):
            fields = dict(extra_fields)
            if not supplied_username:
                fields["username"] = (
                    self._generate_username(email)
                    if attempt == 0
                    else self._retry_username(email, attempt)
                )
            if not supplied_slug:
                fields["slug"] = (
                    self._generate_slug(fields["username"])
                    if attempt == 0
                    else self._retry_slug(fields["username"])
                )
            try:
                with transaction.atomic(using=self._db):
                    user = self.model(email=email, **fields)
                    user.set_password(password)
                    user.save(using=self._db)
                    from organizations.services import create_personal_organization

                    create_personal_organization(user)
                return user
            except IntegrityError:
                identity_taken = self.model.objects.filter(email__iexact=email).exists()
                if supplied_username:
                    identity_taken = (
                        identity_taken
                        or self.model.objects.filter(
                            username__iexact=supplied_username
                        ).exists()
                    )
                if attempt == 4 or identity_taken or supplied_slug:
                    raise
        raise RuntimeError("User creation retry loop exhausted unexpectedly.")

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class PendingEmailChange(models.Model):
    user = models.OneToOneField("User", on_delete=models.CASCADE)
    new_email = models.EmailField()
    auth_version = models.PositiveBigIntegerField()
    token = models.CharField(max_length=64, unique=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"PendingEmailChange(user={self.user_id}, new_email={self.new_email})"


class PendingPasswordReset(models.Model):
    user = models.OneToOneField("User", on_delete=models.CASCADE)
    token = models.CharField(max_length=64, unique=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"PendingPasswordReset(user={self.user_id})"


class PendingRegistration(models.Model):
    email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"PendingRegistration(email={self.email})"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"), name="accounts_pending_registration_email_ci_uniq"
            )
        ]


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True, blank=True)
    slug = models.SlugField(unique=True, blank=True)
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=100, blank=True)
    about = models.TextField(blank=True)
    avatar_path = models.TextField(blank=True, null=True)
    notification_preferences = models.JSONField(default=dict)
    preferred_theme = models.CharField(max_length=16, default="light")
    preferred_language = models.CharField(max_length=16, default="en")
    finished_onboarding = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = None
    auth_version = models.PositiveBigIntegerField(default=1)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_uniq"),
            models.UniqueConstraint(
                Lower("username"), name="accounts_user_username_ci_uniq"
            ),
        ]

    def __str__(self):
        return self.email


class AuthSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="auth_sessions"
    )
    auth_version = models.PositiveBigIntegerField()
    device_name = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "revoked_at"], name="auth_session_user_revoked_idx"
            ),
            models.Index(fields=["expires_at"], name="auth_session_expires_idx"),
        ]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > timezone.now()

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])

    def __str__(self):
        return f"AuthSession(user={self.user_id}, id={self.id})"
