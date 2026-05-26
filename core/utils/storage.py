from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.conf import settings
from functools import lru_cache

import boto3
from botocore.config import Config

def upload_to_storage(filename, content, content_type="image/webp", storage=None):
    """
    Uploads a file to the given storage (default: default_storage).
    - filename: the key/path in storage (e.g. 'avatars/avatar_xxx.webp')
    - content: bytes or file-like object
    - content_type: MIME type (default: image/webp)
    Returns the storage URL for the uploaded file.
    """
    storage = storage or default_storage
    file = ContentFile(content)
    storage.save(filename, file)
    return storage.url(filename)


def _default_storage_options():
    return settings.STORAGES["default"].get("OPTIONS", {})


@lru_cache(maxsize=16)
def _s3_client(endpoint_url, access_key, secret_key, region_name):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region_name,
        config=Config(signature_version="s3v4"),
    )


def generate_presigned_storage_url(
    key,
    *,
    expires_in=3600,
    content_type=None,
    cache_control=None,
    storage_options=None,
):
    options = storage_options or _default_storage_options()
    client = _s3_client(
        options["endpoint_url"],
        options["access_key"],
        options["secret_key"],
        options["region_name"],
    )
    params = {"Bucket": options["bucket_name"], "Key": key}
    if content_type:
        params["ResponseContentType"] = content_type
    if cache_control:
        params["ResponseCacheControl"] = cache_control
    return client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires_in,
    )
