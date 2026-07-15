import uuid

from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils.text import slugify
from ninja.errors import HttpError

from contacts.models import Contact
from tags.models import TaggedItem


def contact_response_queryset():
    return Contact.objects.select_related("organization", "creator").prefetch_related(
        Prefetch("tagged_items", queryset=TaggedItem.objects.select_related("tag"))
    )


def unique_contact_slug(
    organization, display_name: str, exclude_pk: int | None = None
) -> str:
    base = slugify(display_name) or "contact"
    candidate = base
    suffix = 1
    queryset = Contact.objects.filter(organization=organization)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    while queryset.filter(slug=candidate).exists():
        suffix_text = f"-{suffix}"
        candidate = f"{base[: 50 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def display_name_for(data) -> str:
    if data.display_name:
        return data.display_name
    return f"{data.first_name or ''} {data.last_name or ''}".strip()


def create_contact_record(organization, user, data) -> Contact:
    contact_data = data.model_dump(exclude_none=True)
    display_name = display_name_for(data)
    contact_data["display_name"] = display_name
    for attempt in range(5):
        if attempt == 0:
            contact_data["slug"] = unique_contact_slug(organization, display_name)
        else:
            base = slugify(display_name) or "contact"
            contact_data["slug"] = f"{base[:41]}-{uuid.uuid4().hex[:8]}"
        try:
            with transaction.atomic():
                contact = Contact.objects.create(
                    **contact_data,
                    organization=organization,
                    creator=user,
                )
                # A contact cannot have tag relations before its creation commits.
                # Expose that known-empty state without constructing the generic
                # relation manager (which can query Django's content-type table).
                setattr(contact, "_response_tags", [])
                return contact
        except IntegrityError:
            continue
    raise HttpError(409, "A contact with this slug already exists.")


def _normalized_text_fields(values: dict) -> dict:
    nullable_text_fields = {
        "display_name",
        "first_name",
        "last_name",
        "email",
        "location",
        "phone",
        "notes",
    }
    return {
        field: "" if field in nullable_text_fields and value is None else value
        for field, value in values.items()
    }


@transaction.atomic
def replace_contact_record(contact: Contact, data) -> Contact:
    replacement = _normalized_text_fields(data.model_dump())
    replacement["display_name"] = display_name_for(data)
    for field, value in replacement.items():
        setattr(contact, field, value)
    contact.save()
    return contact


@transaction.atomic
def update_contact_record(contact: Contact, data) -> Contact:
    update_fields = data.model_dump(exclude_unset=True)
    update_fields = _normalized_text_fields(update_fields)
    for field, value in update_fields.items():
        setattr(contact, field, value)
    contact.save()
    return contact
