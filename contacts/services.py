from django.db import IntegrityError, transaction
from django.utils.text import slugify
from ninja.errors import HttpError

from contacts.models import Contact


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
    for _attempt in range(3):
        contact_data["slug"] = unique_contact_slug(organization, display_name)
        try:
            with transaction.atomic():
                return Contact.objects.create(
                    **contact_data,
                    organization=organization,
                    creator=user,
                )
        except IntegrityError:
            continue
    raise HttpError(409, "A contact with this slug already exists.")


@transaction.atomic
def update_contact_record(contact: Contact, data) -> Contact:
    update_fields = data.model_dump(exclude_unset=True)
    nullable_text_fields = {
        "first_name",
        "last_name",
        "email",
        "location",
        "phone",
        "notes",
    }
    update_fields = {
        field: "" if field in nullable_text_fields and value is None else value
        for field, value in update_fields.items()
    }
    for field, value in update_fields.items():
        setattr(contact, field, value)
    if update_fields.get("display_name"):
        contact.slug = unique_contact_slug(
            contact.organization, update_fields["display_name"], contact.pk
        )
    try:
        contact.save()
    except IntegrityError as exc:
        raise HttpError(409, "A contact with this slug already exists.") from exc
    return contact
