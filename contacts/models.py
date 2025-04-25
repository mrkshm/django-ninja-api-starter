from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from tags.models import TaggedItem

class Contact(models.Model):
    display_name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    first_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    avatar_path = models.CharField(max_length=255, blank=True, null=True)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="contacts"
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_contacts"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tags = GenericRelation(TaggedItem, related_query_name="contacts")

    def __str__(self):
        return self.display_name
