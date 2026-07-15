from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, RootModel

from core.schemas import DetailResponse
from tags.validation import MAX_TAGS_PER_ASSIGNMENT, TagName


class TagCreate(BaseModel):
    name: TagName
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        json_schema_extra={"examples": [{"name": "vip"}]},
    )


class TagUpdate(BaseModel):
    name: TagName | None = None
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


class TagAssignment(RootModel):
    root: Annotated[
        list[TagName],
        Field(min_length=1, max_length=MAX_TAGS_PER_ASSIGNMENT),
    ]
