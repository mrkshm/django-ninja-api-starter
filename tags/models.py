from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.functions import Lower

from organizations.models import Organization


class Tag(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="tags"
    )
    name = models.CharField(max_length=50)
    slug = models.SlugField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "organization",
                name="tags_tag_org_name_ci_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "slug"),
                name="tags_tag_org_slug_unique",
            ),
        ]


class TaggedItem(models.Model):
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("tag", "content_type", "object_id"),
                name="tags_tagged_item_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("content_type", "object_id"),
                name="tags_tagged_object_idx",
            )
        ]
