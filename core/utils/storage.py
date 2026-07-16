from functools import lru_cache
from typing import Any, cast
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


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
    saved_name = storage.save(filename, file)
    return storage.url(saved_name)


def delete_storage_keys(keys, *, storage=None):
    storage = storage or default_storage
    for key in keys:
        if key:
            storage.delete(key)


def _default_storage_options():
    storages = cast(dict[str, dict[str, Any]], settings.STORAGES)
    return storages["default"].get("OPTIONS", {})


def private_storage_options():
    return _default_storage_options()


def public_storage_options():
    private_options = private_storage_options()
    return {
        **private_options,
        "bucket_name": getattr(settings, "R2_PUBLIC_BUCKET_NAME", None),
    }


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
    bucket_name=None,
):
    options = storage_options or _default_storage_options()
    client = _s3_client(
        options["endpoint_url"],
        options["access_key"],
        options["secret_key"],
        options["region_name"],
    )
    params = {"Bucket": bucket_name or options["bucket_name"], "Key": key}
    if content_type:
        params["ResponseContentType"] = content_type
    if cache_control:
        params["ResponseCacheControl"] = cache_control
    return client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires_in,
    )


def generate_private_presigned_storage_url(key, **kwargs):
    return generate_presigned_storage_url(
        key,
        storage_options=private_storage_options(),
        **kwargs,
    )


def public_storage_url(key):
    base_url = getattr(settings, "IMAGE_PUBLIC_BASE_URL", None)
    if not base_url:
        return default_storage.url(key)
    return f"{base_url.rstrip('/')}/{quote(key, safe='/')}"


def upload_to_public_storage(
    filename, content, content_type="image/webp", storage_options=None
):
    options = storage_options or public_storage_options()
    bucket_name = options.get("bucket_name")
    if not bucket_name:
        upload_to_storage(filename, content, content_type=content_type)
        return public_storage_url(filename)

    client = _s3_client(
        options["endpoint_url"],
        options["access_key"],
        options["secret_key"],
        options["region_name"],
    )
    client.put_object(
        Bucket=bucket_name,
        Key=filename,
        Body=content,
        ContentType=content_type,
    )
    return public_storage_url(filename)


def delete_from_public_storage(filename, storage_options=None):
    options = storage_options or public_storage_options()
    bucket_name = options.get("bucket_name")
    if not bucket_name:
        default_storage.delete(filename)
        return
    client = _s3_client(
        options["endpoint_url"],
        options["access_key"],
        options["secret_key"],
        options["region_name"],
    )
    client.delete_object(Bucket=bucket_name, Key=filename)


def public_storage_exists(filename, storage_options=None) -> bool:
    options = storage_options or public_storage_options()
    bucket_name = options.get("bucket_name")
    if not bucket_name:
        return default_storage.exists(filename)
    client = _s3_client(
        options["endpoint_url"],
        options["access_key"],
        options["secret_key"],
        options["region_name"],
    )
    try:
        client.head_object(Bucket=bucket_name, Key=filename)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {
            "404",
            "NoSuchKey",
            "NotFound",
        }:
            return False
        raise
    return True
