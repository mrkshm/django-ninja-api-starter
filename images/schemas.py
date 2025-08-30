from pydantic import BaseModel, Field, field_serializer, ConfigDict
from typing import Optional, List
from datetime import datetime

class ImageCreate(BaseModel):
    file: Optional[str] = None  # Accepts file path or URL; actual upload handled separately
    description: Optional[str] = None
    alt_text: Optional[str] = None
    title: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ImagePatchIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    alt_text: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class ImageUpdate(BaseModel):
    description: Optional[str] = None
    alt_text: Optional[str] = None
    title: Optional[str] = None

class ImageVariants(BaseModel):
    original: Optional[str] = None
    thumb: Optional[str] = None
    sm: Optional[str] = None
    md: Optional[str] = None
    lg: Optional[str] = None


class ImageOut(BaseModel):
    id: int
    file: str
    url: Optional[str] = None
    variants: Optional[ImageVariants] = None
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
        model_config = ConfigDict(from_attributes=True)

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
    model_config = ConfigDict(from_attributes=True)


class BulkAttachOut(BaseModel):
    attached: List[int]


class BulkDetachOut(BaseModel):
    detached: List[int]


class SetCoverIn(BaseModel):
    image_id: int