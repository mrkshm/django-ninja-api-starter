from typing import Annotated

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from pydantic import AfterValidator, StringConstraints, WithJsonSchema

MAX_EMAIL_LENGTH = 254


def normalize_and_validate_email(value: str) -> str:
    normalized = value.strip().lower()
    try:
        validate_email(normalized)
    except DjangoValidationError as exc:
        raise ValueError("Invalid email address") from exc
    return normalized


AccountEmail = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=MAX_EMAIL_LENGTH,
    ),
    AfterValidator(normalize_and_validate_email),
    WithJsonSchema(
        {
            "type": "string",
            "format": "email",
            "minLength": 3,
            "maxLength": MAX_EMAIL_LENGTH,
        }
    ),
]

GenericEmailInput = Annotated[
    str,
    StringConstraints(max_length=MAX_EMAIL_LENGTH),
]
