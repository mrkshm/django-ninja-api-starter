from typing import List, Optional

from ninja import Schema
from pydantic import ConfigDict


class BulkDeleteResponse(Schema):
    id: Optional[int] = None
    status: str
    error: Optional[str] = None


class BulkUploadResponse(Schema):
    id: Optional[int] = None
    file: Optional[str] = None
    status: str
    error: Optional[str] = None


class BulkImageIdsIn(Schema):
    image_ids: List[int]
    model_config = ConfigDict(extra="forbid")


class ImageIdsIn(Schema):
    image_ids: list[int]
    model_config = ConfigDict(extra="forbid")


class ReorderIn(Schema):
    image_ids: list[int]
    model_config = ConfigDict(extra="forbid")
