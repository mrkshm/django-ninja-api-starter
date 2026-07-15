from typing import Annotated

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from pydantic import AfterValidator, StringConstraints, WithJsonSchema

MAX_CONTACT_TEXT_LENGTH = 255
MAX_CONTACT_EMAIL_LENGTH = 254
MAX_CONTACT_PHONE_LENGTH = 20
MAX_CONTACT_NOTES_LENGTH = 10_000
MAX_CONTACT_SEARCH_LENGTH = 200
MAX_CONTACT_SEARCH_TERMS = 10

ContactText = Annotated[
    str,
    StringConstraints(max_length=MAX_CONTACT_TEXT_LENGTH),
]
ContactPhone = Annotated[
    str,
    StringConstraints(max_length=MAX_CONTACT_PHONE_LENGTH),
]
ContactNotes = Annotated[
    str,
    StringConstraints(max_length=MAX_CONTACT_NOTES_LENGTH),
]


def validate_contact_email(value: str) -> str:
    clean_value = value.strip()
    if not clean_value:
        raise ValueError("Email cannot be blank; use null to clear it")
    try:
        validate_email(clean_value)
    except DjangoValidationError as exc:
        raise ValueError("Invalid email address") from exc
    return clean_value


ContactEmail = Annotated[
    str,
    StringConstraints(max_length=MAX_CONTACT_EMAIL_LENGTH),
    AfterValidator(validate_contact_email),
    WithJsonSchema(
        {
            "type": "string",
            "format": "email",
            "maxLength": MAX_CONTACT_EMAIL_LENGTH,
        }
    ),
]
