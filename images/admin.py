from django.contrib import admin
from django.utils.html import format_html

from .models import Image, ImageShareLink, PolymorphicImageRelation


# Register your models here.
@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    readonly_fields = (
        "file",
        "thumbnail",
    )
    list_display = (
        "id",
        "thumbnail",
        "title",
        "visibility",
        "organization",
        "creator",
        "created_at",
    )
    search_fields = ("title", "description", "alt_text")
    list_filter = ("visibility", "organization", "creator")
    fields = (
        "file",
        "thumbnail",
        "title",
        "visibility",
        "description",
        "alt_text",
        "organization",
        "creator",
    )

    @admin.display(description="Thumbnail")
    def thumbnail(self, obj):
        if obj.file:
            # If you have a dedicated thumbnail version, adjust the URL accordingly
            url = obj.file.url
            # If you store thumbnails with a suffix, e.g. _thumb.webp, you can swap here
            if url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                base, ext = url.rsplit(".", 1)
                thumb_url = f"{base}_thumb.webp"
            else:
                thumb_url = url
            return format_html(
                '<img src="{}" width="60" style="object-fit:cover; border-radius:4px;" />',
                thumb_url,
            )
        return ""

    def has_add_permission(self, request):
        return False


@admin.register(PolymorphicImageRelation)
class PolymorphicImageRelationAdmin(admin.ModelAdmin):
    pass


@admin.register(ImageShareLink)
class ImageShareLinkAdmin(admin.ModelAdmin):
    readonly_fields = ("token_hash", "created_at")
    list_display = (
        "id",
        "image",
        "created_by",
        "created_at",
        "expires_at",
        "revoked_at",
    )
    search_fields = ("image__title", "image__file")
    list_filter = ("revoked_at", "expires_at")
