from django.contrib import admin

from .models import Tag, TaggedItem


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "organization_id")
    search_fields = ("name", "slug", "organization__name", "organization__slug")
    raw_id_fields = ("organization",)
    list_select_related = ("organization",)


@admin.register(TaggedItem)
class TaggedItemAdmin(admin.ModelAdmin):
    list_display = ("id", "tag_id", "content_type_id", "object_id")
    search_fields = ("tag__name", "tag__slug")
    raw_id_fields = ("tag", "content_type")
    list_select_related = ("tag", "content_type")
