from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from organizations.models import Organization

class Tag(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=50)
    slug = models.SlugField()

    class Meta:
        unique_together = (('organization', 'name'), ('organization', 'slug'))

class TaggedItem(models.Model):
    tag          = models.ForeignKey(Tag, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id    = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        unique_together = (('tag','content_type','object_id'),)