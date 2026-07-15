from django.contrib import admin

from .models import ExportJob, Membership, Organization

# Register your models here.
admin.site.register(Organization)
admin.site.register(Membership)


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
    readonly_fields = (
        "created_at",
        "queued_at",
        "started_at",
        "heartbeat_at",
        "completed_at",
        "attempt_count",
    )
