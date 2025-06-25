from django.db import models
from django.db.models import Q
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from organizations.models import Organization
from django.conf import settings

from core.utils.utils import generate_upload_filename

# Create your models here.

def image_upload_to(instance, filename):
    # Always use a string prefix for generate_upload_filename
    return generate_upload_filename("image", filename)

class Image(models.Model):
    file = models.ImageField(upload_to=image_upload_to)
    description = models.TextField(blank=True, null=True)
    alt_text = models.CharField(max_length=120, blank=True, null=True)
    title = models.CharField(max_length=120, blank=True, null=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="images")
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_images"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title or f"Image {self.pk}"

class PolymorphicImageRelation(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name="relations")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    is_cover = models.BooleanField(default=False)
    order = models.IntegerField(blank=True, null=True)
    custom_description = models.TextField(blank=True, null=True)
    custom_alt_text = models.CharField(max_length=120, blank=True, null=True)
    custom_title = models.CharField(max_length=120, blank=True, null=True)

    class Meta:
        unique_together = ('image', 'content_type', 'object_id')
        ordering = ['order', 'pk']
        constraints = [
            # Ensure at most one primary (is_cover=True) per (content_type, object_id)
            models.UniqueConstraint(
                fields=["content_type", "object_id", "is_cover"],
                condition=Q(is_cover=True),
                name="uniq_primary_per_object",
            ),
        ]
        indexes = [
            models.Index(fields=["content_type", "object_id", "order"], name="rel_obj_order_idx"),
        ]

    def __str__(self):
        return f"{self.content_object} - {self.image}"
