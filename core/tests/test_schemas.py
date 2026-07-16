import pytest
from pydantic import ValidationError

from accounts.schemas import (
    ChangePasswordSchema,
    DeleteAccountSchema,
    EmailSchema,
    EmailUpdateSchema,
    PasswordResetRequestSchema,
    PasswordResetSchema,
    RegisterSchema,
    TokenPairInputSchema,
    UserProfileUpdate,
)
from accounts.username import UsernameUpdateSchema
from contacts.schemas import ContactIn, ContactUpdate
from contacts.schemas import DetailResponse as ContactDetailResponse
from core.schemas import DetailResponse
from images.api_schemas import BulkImageIdsIn, ImageIdsIn, ReorderIn
from images.schemas import (
    CreateImageShareIn,
)
from images.schemas import DetailResponse as ImageDetailResponse
from images.schemas import (
    ImageCreate,
    ImagePatchIn,
    ImageUpdate,
    SetCoverIn,
)
from tags.schemas import DetailResponse as TagDetailResponse
from tags.schemas import TagCreate, TagUpdate


def test_detail_response_is_shared_schema():
    assert ContactDetailResponse is DetailResponse
    assert ImageDetailResponse is DetailResponse
    assert TagDetailResponse is DetailResponse
    assert DetailResponse(detail="ok").detail == "ok"


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (TokenPairInputSchema, {"email": "user@example.com", "password": "pw"}),
        (RegisterSchema, {"email": "user@example.com", "password": "pw"}),
        (ChangePasswordSchema, {"old_password": "old", "new_password": "new"}),
        (DeleteAccountSchema, {"password": "pw"}),
        (EmailUpdateSchema, {"email": "new@example.com"}),
        (EmailSchema, {"email": "user@example.com"}),
        (PasswordResetRequestSchema, {"email": "user@example.com"}),
        (PasswordResetSchema, {"token": "token", "new_password": "new"}),
        (UserProfileUpdate, {"first_name": "Ada"}),
        (UsernameUpdateSchema, {"username": "ada"}),
        (ContactIn, {"display_name": "Ada"}),
        (ContactUpdate, {"display_name": "Ada"}),
        (ImageCreate, {"title": "Cover"}),
        (ImagePatchIn, {"title": "Cover"}),
        (ImageUpdate, {"title": "Cover"}),
        (SetCoverIn, {"image_id": 1}),
        (CreateImageShareIn, {"expires_in_seconds": 3600}),
        (BulkImageIdsIn, {"image_ids": [1]}),
        (ImageIdsIn, {"image_ids": [1]}),
        (ReorderIn, {"image_ids": [1]}),
        (TagCreate, {"name": "jazz"}),
        (TagUpdate, {"name": "jazz"}),
    ],
)
def test_input_schemas_reject_unknown_fields(schema, payload):
    with pytest.raises(ValidationError):
        schema.model_validate({**payload, "unexpected": "ignored before"})
