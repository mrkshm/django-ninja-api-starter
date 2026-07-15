from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils.text import slugify
from ninja.errors import HttpError

from tags.models import Tag, TaggedItem
from tags.validation import MAX_TAGS_PER_ASSIGNMENT, normalize_tag_name


@dataclass(frozen=True)
class TagAssignmentResult:
    tags: list[Tag]
    newly_assigned_tag_ids: list[int]


def _canonical_name(name: str) -> tuple[str, str]:
    try:
        clean_name = normalize_tag_name(name)
    except (AttributeError, TypeError, ValueError) as exc:
        raise HttpError(400, str(exc)) from exc
    return clean_name, slugify(clean_name)


def _slug_collision() -> HttpError:
    return HttpError(
        409,
        "Two different tag names cannot share the same slug in an organization.",
    )


@transaction.atomic
def create_tag(organization, name: str) -> Tag:
    clean_name, slug = _canonical_name(name)
    try:
        return Tag.objects.create(
            organization=organization,
            name=clean_name,
            slug=slug,
        )
    except IntegrityError as exc:
        raise HttpError(
            409, "A tag with this name or slug already exists in this organization."
        ) from exc


@transaction.atomic
def rename_tag(tag: Tag, name: str) -> Tag:
    clean_name, slug = _canonical_name(name)
    tag.name = clean_name
    tag.slug = slug
    try:
        tag.save(update_fields=["name", "slug"])
    except IntegrityError as exc:
        raise HttpError(
            409, "A tag with this name or slug already exists in this organization."
        ) from exc
    return tag


@transaction.atomic
def assign_tags_to_object(
    organization,
    content_type,
    object_id: int,
    names: list[str],
) -> TagAssignmentResult:
    if not 1 <= len(names) <= MAX_TAGS_PER_ASSIGNMENT:
        raise HttpError(
            400,
            f"Assign between 1 and {MAX_TAGS_PER_ASSIGNMENT} tags at a time.",
        )

    requested: dict[str, str] = {}
    for name in names:
        clean_name, slug = _canonical_name(name)
        prior_name = requested.get(slug)
        if prior_name is not None:
            if prior_name.casefold() != clean_name.casefold():
                raise _slug_collision()
            continue
        requested[slug] = clean_name

    existing_by_slug = {
        tag.slug: tag
        for tag in Tag.objects.filter(
            organization=organization,
            slug__in=requested,
        )
    }
    for slug, tag in existing_by_slug.items():
        if tag.name.casefold() != requested[slug].casefold():
            raise _slug_collision()

    Tag.objects.bulk_create(
        [
            Tag(organization=organization, slug=slug, name=name)
            for slug, name in requested.items()
            if slug not in existing_by_slug
        ],
        ignore_conflicts=True,
    )
    tags_by_slug = {
        tag.slug: tag
        for tag in Tag.objects.filter(
            organization=organization,
            slug__in=requested,
        )
    }
    if set(tags_by_slug) != set(requested):
        raise _slug_collision()
    for slug, tag in tags_by_slug.items():
        if tag.name.casefold() != requested[slug].casefold():
            raise _slug_collision()

    ordered_tags = [tags_by_slug[slug] for slug in requested]
    tag_ids = [tag.id for tag in ordered_tags]
    existing_relation_ids = set(
        TaggedItem.objects.filter(
            tag_id__in=tag_ids,
            content_type=content_type,
            object_id=object_id,
        ).values_list("tag_id", flat=True)
    )
    TaggedItem.objects.bulk_create(
        [
            TaggedItem(
                tag=tag,
                content_type=content_type,
                object_id=object_id,
            )
            for tag in ordered_tags
            if tag.id not in existing_relation_ids
        ],
        ignore_conflicts=True,
    )
    return TagAssignmentResult(
        tags=ordered_tags,
        newly_assigned_tag_ids=[
            tag.id for tag in ordered_tags if tag.id not in existing_relation_ids
        ],
    )
