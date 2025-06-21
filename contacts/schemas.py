from typing import Optional
from pydantic import BaseModel, model_validator

from tags.schemas import TagOut

class ContactIn(BaseModel):
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    avatar_path: Optional[str] = None
    organization: Optional[str] = None  # Optional organization slug

    @model_validator(mode="after")
    def at_least_one_name(self):
        if not (self.display_name or self.first_name or self.last_name):
            raise ValueError("At least one of display_name, first_name, or last_name must be provided.")
        return self

class ContactOut(BaseModel):
    display_name: str
    slug: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    avatar_path: Optional[str] = None
    organization: str
    creator: Optional[str] = None  # User slug
    tags: list[TagOut]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

class ContactAvatarResponse(BaseModel):
    avatar_path: Optional[str] = None
    avatar_url: Optional[str] = None
    large_avatar_url: Optional[str] = None

class DetailResponse(BaseModel):
    detail: str