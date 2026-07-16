from django.contrib import admin

from .models import Contact


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "display_name",
        "email",
        "organization_id",
        "creator_id",
        "updated_at",
    )
    search_fields = (
        "display_name",
        "first_name",
        "last_name",
        "email",
        "organization__name",
        "organization__slug",
    )
    raw_id_fields = ("organization", "creator")
    list_select_related = ("organization", "creator")
