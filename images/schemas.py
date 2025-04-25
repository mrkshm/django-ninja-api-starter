from pydantic import BaseModel, Field, field_serializer
from typing import Optional
from datetime import datetime

class ImageCreate(BaseModel):
    file: Optional[str] = None  # Accepts file path or URL; actual upload handled separately
    description: Optional[str] = None
    alt_text: Optional[str] = None
    title: Optional[str] = None

    class Config:
        from_attributes = True

class ImageUpdate(BaseModel):
    description: Optional[str] = None
    alt_text: Optional[str] = None
    title: Optional[str] = None

class ImageOut(BaseModel):
    id: int
    file: str
    description: Optional[str] = None
    alt_text: Optional[str] = None
    title: Optional[str] = None
    organization: int = Field(..., alias="organization_id")
    creator: Optional[int] = Field(None, alias="creator_id")
    created_at: str
    updated_at: str

    @field_serializer("file")
    def serialize_file(self, v):
        # Return the file path as a string
        return str(v) if v else None

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, v):
        # Return ISO format string
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v) if v else None

    class Config:
        from_attributes = True

class PolymorphicImageRelationOut(BaseModel):
    id: int
    image: ImageOut
    is_cover: bool
    order: Optional[int] = None
    custom_description: Optional[str] = None
    custom_alt_text: Optional[str] = None
    custom_title: Optional[str] = None
    object_id: int
    content_type: str  # e.g. "contacts.contact"

    class Config:
        from_attributes = True