from typing import List, Optional

from ninja import Schema


class BulkDeleteResponse(Schema):
    id: int = None
    status: str
    error: str = None


class BulkUploadResponse(Schema):
    id: int = None
    file: str = None
    status: str
    error: Optional[str] = None


class BulkImageIdsIn(Schema):
    image_ids: List[int]


class ImageIdsIn(Schema):
    image_ids: list[int]


class ReorderIn(Schema):
    image_ids: list[int]
