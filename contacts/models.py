from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from core.utils.storage import public_storage_url
from tags.models import TaggedItem


class Contact(models.Model):
    display_name = models.CharField(max_length=255)
    slug = models.SlugField(blank=True)
    first_name = models.CharField(max_length=255, blank=True, default="")
    last_name = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    location = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    avatar_path = models.CharField(max_length=255, blank=True, null=True)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="contacts"
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_contacts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tagged_items = GenericRelation(TaggedItem, related_query_name="contacts")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "slug"),
                name="contacts_contact_org_slug_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("organization", "display_name"),
                name="contacts_org_display_name_idx",
            ),
            models.Index(
                fields=("organization", "created_at"),
                name="contacts_org_created_idx",
            ),
        ]

    @property
    def tags(self):
        return [item.tag for item in self.tagged_items.all()]

    @property
    def organization_slug(self):
        return self.organization.slug

    @property
    def creator_slug(self):
        return self.creator.slug if self.creator else None

    @property
    def avatar_url(self):
        return public_storage_url(self.avatar_path) if self.avatar_path else None

    @property
    def large_avatar_url(self):
        if not self.avatar_path:
            return None
        stem, extension = self.avatar_path.rsplit(".", 1)
        return public_storage_url(f"{stem}_lg.{extension}")

    def __str__(self):
        return self.display_name
