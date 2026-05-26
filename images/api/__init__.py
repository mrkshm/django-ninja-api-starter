import os
from importlib import import_module

from django.core.files.storage import default_storage
from django.http import JsonResponse

from core.utils.idempotency import HEADER_NAME, read_cached_response, store_cached_response
from core.utils.image import resize_images
from core.utils.storage import upload_to_storage
from core.utils.utils import generate_upload_filename
from images.api.common import get_org_for_request, logger, router
from images.api_schemas import (
    BulkDeleteResponse,
    BulkImageIdsIn,
    BulkUploadResponse,
    ImageIdsIn,
    ReorderIn,
)
from images.throttles import (
    LoggingUserRateThrottle,
    bulk_attach_throttle,
    bulk_delete_throttle,
    bulk_detach_throttle,
    bulk_upload_throttle,
    upload_throttle,
)

_listing = import_module("images.api.listing")
_relations = import_module("images.api.relations")
_ordering = import_module("images.api.ordering")
_metadata = import_module("images.api.metadata")
_uploads = import_module("images.api.uploads")
_deletion = import_module("images.api.deletion")
_access = import_module("images.api.access")

list_images_for_org = _listing.list_images_for_org
list_images_for_object = _listing.list_images_for_object
attach_images = _relations.attach_images
bulk_attach_images = _relations.bulk_attach_images
bulk_detach_images = _relations.bulk_detach_images
remove_image_from_object = _relations.remove_image_from_object
reorder_images = _ordering.reorder_images
set_cover_image = _ordering.set_cover_image
unset_cover_image = _ordering.unset_cover_image
edit_image_metadata = _metadata.edit_image_metadata
upload_image = _uploads.upload_image
bulk_upload_images = _uploads.bulk_upload_images
delete_image = _deletion.delete_image
bulk_delete_images = _deletion.bulk_delete_images
get_image_signed_urls = _access.get_image_signed_urls
create_image_share = _access.create_image_share
revoke_image_share = _access.revoke_image_share
get_shared_image_signed_urls = _access.get_shared_image_signed_urls


def custom_validation_error(request, exc):
    return JsonResponse({"detail": str(exc)}, status=400)


__all__ = [
    "BulkDeleteResponse",
    "BulkImageIdsIn",
    "BulkUploadResponse",
    "HEADER_NAME",
    "ImageIdsIn",
    "LoggingUserRateThrottle",
    "ReorderIn",
    "attach_images",
    "bulk_attach_images",
    "bulk_attach_throttle",
    "bulk_delete_images",
    "bulk_delete_throttle",
    "bulk_detach_images",
    "bulk_detach_throttle",
    "bulk_upload_images",
    "bulk_upload_throttle",
    "custom_validation_error",
    "create_image_share",
    "default_storage",
    "delete_image",
    "edit_image_metadata",
    "generate_upload_filename",
    "get_image_signed_urls",
    "get_org_for_request",
    "get_shared_image_signed_urls",
    "list_images_for_object",
    "list_images_for_org",
    "logger",
    "os",
    "read_cached_response",
    "remove_image_from_object",
    "reorder_images",
    "revoke_image_share",
    "resize_images",
    "router",
    "set_cover_image",
    "store_cached_response",
    "unset_cover_image",
    "upload_image",
    "upload_throttle",
    "upload_to_storage",
]
