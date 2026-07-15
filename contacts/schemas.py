from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.schemas import DetailResponse as CoreDetailResponse
from tags.schemas import TagOut

DetailResponse = CoreDetailResponse


class ContactIn(BaseModel):
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def at_least_one_name(self):
        if not (self.display_name or self.first_name or self.last_name):
            raise ValueError(
                "At least one of display_name, first_name, or last_name "
                "must be provided."
            )
        return self


class ContactUpdate(BaseModel):
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


class ContactOut(BaseModel):
    id: int
    display_name: str
    slug: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    avatar_path: Optional[str] = None
    # Map model attributes to the public organization and creator fields.
    organization: str = Field(validation_alias="organization_slug")
    creator: Optional[str] = Field(default=None, validation_alias="creator_slug")
    tags: list[TagOut]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContactAvatarResponse(BaseModel):
    avatar_path: Optional[str] = None
    avatar_url: Optional[str] = None
    large_avatar_url: Optional[str] = None
