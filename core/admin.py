from django.contrib import admin

from core.models import IdempotencyRecord


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = (
        "identity_hash",
        "user",
        "method",
        "path",
        "status_code",
        "completed_at",
        "expires_at",
    )
    search_fields = ("identity_hash", "user__email", "path")
    list_filter = ("method", "status_code", "completed_at", "expires_at")
    readonly_fields = (
        "identity_hash",
        "request_fingerprint",
        "user",
        "method",
        "path",
        "status_code",
        "response_data",
        "created_at",
        "completed_at",
        "expires_at",
    )

    def has_add_permission(self, request):
        return False
