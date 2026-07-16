from typing import Annotated

from django.utils.text import slugify
from pydantic import AfterValidator, StringConstraints

MAX_TAG_NAME_LENGTH = 50
MAX_TAGS_PER_ASSIGNMENT = 50


def normalize_tag_name(value: str) -> str:
    clean_name = value.strip()
    if not clean_name:
        raise ValueError("Tag names cannot be empty.")
    if len(clean_name) > MAX_TAG_NAME_LENGTH:
        raise ValueError(f"Tag names cannot exceed {MAX_TAG_NAME_LENGTH} characters.")
    if not slugify(clean_name):
        raise ValueError("Tag names must contain at least one letter or number.")
    return clean_name


TagName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_TAG_NAME_LENGTH,
    ),
    AfterValidator(normalize_tag_name),
]
