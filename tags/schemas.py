# tags/schemas.py
from pydantic import BaseModel, Field, ConfigDict

class TagCreate(BaseModel):
    name: str
    model_config = ConfigDict(from_attributes=True)

class TagUpdate(BaseModel):
    name: str | None = None

class TagOut(BaseModel):
    id: int
    name: str
    slug: str
    organization: int = Field(..., alias="organization_id")
    model_config = ConfigDict(from_attributes=True)

class TaggedItemOut(BaseModel):
    tag: TagOut
    object_id: int
    content_type: str  # e.g. "contacts.contact"
    model_config = ConfigDict(from_attributes=True)