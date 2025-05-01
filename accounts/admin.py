from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, PendingEmailChange, PendingPasswordReset

# Register your models here.

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ("id", "email", "username", "first_name", "last_name", "is_staff", "is_active", "created_at")
    list_filter = ("is_staff", "is_active", "preferred_language", "preferred_theme")
    search_fields = ("email", "username", "first_name", "last_name")
    ordering = ("id",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("username", "slug", "first_name", "last_name", "location", "about", "avatar_path")}),
        ("Preferences", {"fields": ("notification_preferences", "preferred_theme", "preferred_language", "finished_onboarding")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "is_staff", "is_active")
        }),
    )
    readonly_fields = ("created_at", "updated_at", "last_login")

@admin.register(PendingEmailChange)
class PendingEmailChangeAdmin(admin.ModelAdmin):
    list_display = ("user", "new_email", "created_at", "expires_at")
    search_fields = ("user__email", "new_email")
    list_filter = ("created_at", "expires_at")

@admin.register(PendingPasswordReset)
class PendingPasswordResetAdmin(admin.ModelAdmin):
    list_display = ("user", "token", "created_at", "expires_at")
    search_fields = ("user__email", "token")
    list_filter = ("created_at", "expires_at")
