# tags/schemas.py
from pydantic import BaseModel, Field

class TagCreate(BaseModel):
    name: str
    slug: str

    class Config:
        from_attributes = True

class TagUpdate(BaseModel):
    name: str | None = None

class TagOut(BaseModel):
    id: int
    name: str
    slug: str
    organization: int = Field(..., alias="organization_id")

    class Config:
        from_attributes = True

class TaggedItemOut(BaseModel):
    tag: TagOut
    object_id: int
    content_type: str  # e.g. "contacts.contact"

    class Config:
        from_attributes = True