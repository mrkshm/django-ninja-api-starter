from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils.text import slugify
from django.utils import timezone
import secrets
from core.utils import make_it_unique
import string
from django.core.cache import cache

class UserManager(BaseUserManager):
    def _clean_username(self, username):
        # Allow only alphanumerics, dots, and underscores
        allowed = set(string.ascii_letters + string.digits + '._')
        return ''.join(c for c in username if c in allowed)

    def _generate_username(self, email):
        base_username = self._clean_username(email.split('@')[0])
        return make_it_unique(base_username, self.model, "username")

    def _generate_slug(self, username):
        base_slug = slugify(username)
        return make_it_unique(base_slug, self.model, "slug")

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        if not extra_fields.get("username"):
            extra_fields["username"] = self._generate_username(email)
        if not extra_fields.get("slug"):
            extra_fields["slug"] = self._generate_slug(extra_fields["username"])
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)

class PendingEmailChange(models.Model):
    user = models.ForeignKey('User', on_delete=models.CASCADE)
    new_email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"PendingEmailChange(user={self.user_id}, new_email={self.new_email})"

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
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def get_user_permissions(self):
        cache_key = f'user_permissions_{self.id}'
        permissions = cache.get(cache_key)
        if permissions is None:
            permissions = super().get_user_permissions()
            cache.set(cache_key, permissions, timeout=3600)  # 1 hour
        return permissions

    def __str__(self):
        return self.email