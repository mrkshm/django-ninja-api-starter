# tags/schemas.py
from pydantic import BaseModel, Field, ConfigDict

from core.schemas import DetailResponse

class TagCreate(BaseModel):
    name: str
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        json_schema_extra={"examples": [{"name": "vip"}]},
    )

class TagUpdate(BaseModel):
    name: str | None = None
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"name": "priority"}]},
    )

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


class RemovedCountResponse(BaseModel):
    removed_count: int
    model_config = ConfigDict(json_schema_extra={"examples": [{"removed_count": 2}]})
