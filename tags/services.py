from django.db import IntegrityError, transaction
from django.utils.text import slugify
from ninja.errors import HttpError

from tags.models import Tag


@transaction.atomic
def create_tag(organization, name: str) -> Tag:
    clean_name = name.strip()
    try:
        return Tag.objects.create(
            organization=organization,
            name=clean_name,
            slug=slugify(clean_name) or "tag",
        )
    except IntegrityError as exc:
        raise HttpError(
            409, "A tag with this name or slug already exists in this organization."
        ) from exc


@transaction.atomic
def rename_tag(tag: Tag, name: str) -> Tag:
    tag.name = name.strip()
    tag.slug = slugify(tag.name) or "tag"
    try:
        tag.save(update_fields=["name", "slug"])
    except IntegrityError as exc:
        raise HttpError(
            409, "A tag with this name or slug already exists in this organization."
        ) from exc
    return tag
