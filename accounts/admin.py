from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import transaction

from .models import (
    AuthSession,
    PendingEmailChange,
    PendingPasswordReset,
    PendingRegistration,
    User,
)
from .services import set_user_active_status

# Register your models here.


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = (
        "id",
        "email",
        "username",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
        "created_at",
    )
    list_filter = ("is_staff", "is_active", "preferred_language", "preferred_theme")
    search_fields = ("email", "username", "first_name", "last_name")
    ordering = ("id",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "username",
                    "slug",
                    "first_name",
                    "last_name",
                    "location",
                    "about",
                    "avatar_path",
                )
            },
        ),
        (
            "Preferences",
            {
                "fields": (
                    "notification_preferences",
                    "preferred_theme",
                    "preferred_language",
                    "finished_onboarding",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "is_staff", "is_active"),
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at")
    actions = ("deactivate_selected_users", "activate_selected_users")

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        previous_is_active = None
        if obj.pk:
            previous_is_active = (
                User.objects.filter(pk=obj.pk)
                .values_list("is_active", flat=True)
                .first()
            )
        super().save_model(request, obj, form, change)
        if previous_is_active is not None and previous_is_active != obj.is_active:
            set_user_active_status(obj, is_active=obj.is_active)

    @admin.action(description="Deactivate selected users and revoke their sessions")
    def deactivate_selected_users(self, request, queryset):
        for user in queryset.iterator():
            set_user_active_status(user, is_active=False)

    @admin.action(description="Activate selected users with fresh session state")
    def activate_selected_users(self, request, queryset):
        for user in queryset.iterator():
            set_user_active_status(user, is_active=True)


class PendingTokenAdmin(admin.ModelAdmin):
    """Pending credentials are inspectable and deletable, never hand-authored."""

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(PendingEmailChange)
class PendingEmailChangeAdmin(PendingTokenAdmin):
    list_display = ("user", "new_email", "auth_version", "created_at", "expires_at")
    search_fields = ("user__email", "new_email")
    list_filter = ("created_at", "expires_at")


@admin.register(PendingPasswordReset)
class PendingPasswordResetAdmin(PendingTokenAdmin):
    list_display = ("user", "created_at", "expires_at")
    search_fields = ("user__email", "token")
    list_filter = ("created_at", "expires_at")


@admin.register(PendingRegistration)
class PendingRegistrationAdmin(PendingTokenAdmin):
    list_display = ("email", "created_at", "expires_at")
    search_fields = ("email",)
    list_filter = ("created_at", "expires_at")


@admin.register(AuthSession)
class AuthSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "device_name",
        "created_at",
        "last_used_at",
        "expires_at",
        "revoked_at",
    )
    search_fields = ("id", "user__email", "device_name")
    list_filter = ("created_at", "expires_at", "revoked_at")
    readonly_fields = (
        "id",
        "user",
        "auth_version",
        "device_name",
        "created_at",
        "last_used_at",
        "expires_at",
        "revoked_at",
    )

    def has_add_permission(self, request):
        return False
