from django.contrib import admin

from .models import ExportJob, Membership, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "type", "creator_id", "created_at")
    list_filter = ("type",)
    search_fields = ("name", "slug", "creator__email", "creator__username")
    raw_id_fields = ("creator",)
    list_select_related = ("creator",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "organization_id", "role", "created_at")
    list_filter = ("role",)
    search_fields = (
        "user__email",
        "user__username",
        "organization__name",
        "organization__slug",
    )
    raw_id_fields = ("user", "organization")
    list_select_related = ("user", "organization")


@admin.register(ExportJob)
class ExportJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "organization",
        "status",
        "attempt_count",
        "queued_at",
        "heartbeat_at",
        "completed_at",
    )
    list_filter = ("status",)
    search_fields = ("id", "organization__name", "organization__slug")
    raw_id_fields = ("organization", "requested_by")
    list_select_related = ("organization", "requested_by")
    readonly_fields = (
        "created_at",
        "queued_at",
        "started_at",
        "heartbeat_at",
        "completed_at",
        "attempt_count",
    )
