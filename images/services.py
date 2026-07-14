import mimetypes
import os
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.core.files.storage import default_storage
from django.utils import timezone

from core.utils.image import InvalidImageContent, normalize_image_bytes, resize_images
from core.utils.storage import generate_private_presigned_storage_url
from core.utils.storage import delete_storage_keys, upload_to_storage
from images.models import Image
from images.serializers import build_variant_keys
from images.schemas import ImageSignedUrls, ImageSignedUrlsOut

DEFAULT_SIGNED_URL_TTL_SECONDS = 15 * 60
logger = logging.getLogger(__name__)


class ImageUploadFailed(RuntimeError):
    pass


def signed_url_ttl_seconds() -> int:
    return int(
        getattr(
            settings, "IMAGE_SIGNED_URL_TTL_SECONDS", DEFAULT_SIGNED_URL_TTL_SECONDS
        )
    )


def image_variant_keys(image: Image) -> dict[str, str]:
    file_name = (
        image.file.name or str(image.file)
        if hasattr(image.file, "name")
        else str(image.file)
    )
    return build_variant_keys(file_name).model_dump()


def upload_image_file(file, organization, *, creator_id=None) -> Image:
    original_name = file.name or "image"
    data = file.read()
    try:
        normalized = normalize_image_bytes(data)
        variants_bytes = resize_images(normalized)
    except InvalidImageContent:
        raise
    except Exception as exc:
        logger.exception("images:processing_failed org=%s", organization.id)
        raise ImageUploadFailed("Image processing failed.") from exc

    token = secrets.token_hex(24)
    filename = f"private/images/{organization.pk}/{token}.webp"
    base, _ext = os.path.splitext(filename)
    uploaded_keys: list[str] = []
    try:
        upload_to_storage(filename, normalized, content_type="image/webp")
        uploaded_keys.append(filename)
        for key, content in variants_bytes.items():
            variant_key = f"{base}_{key}.webp"
            upload_to_storage(variant_key, content, content_type="image/webp")
            uploaded_keys.append(variant_key)
        try:
            return Image.objects.create(
                file=filename,
                organization=organization,
                creator_id=creator_id,
                title=original_name,
                description="",
                alt_text="",
            )
        except Exception:
            delete_storage_keys(uploaded_keys)
            raise
    except Exception as exc:
        delete_storage_keys(uploaded_keys)
        logger.exception("images:storage_write_failed org=%s", organization.id)
        raise ImageUploadFailed("Image upload failed.") from exc


def sign_image_variant_urls(
    image: Image,
    *,
    expires_in: int | None = None,
) -> ImageSignedUrlsOut:
    ttl = expires_in or signed_url_ttl_seconds()
    keys = image_variant_keys(image)
    urls = {
        variant: generate_private_presigned_storage_url(
            key,
            expires_in=ttl,
            content_type=mimetypes.guess_type(key)[0],
            cache_control=f"private, max-age={ttl}",
        )
        for variant, key in keys.items()
    }
    expires_at = timezone.now() + timedelta(seconds=ttl)
    return ImageSignedUrlsOut(
        image_id=image.id,
        expires_at=expires_at.isoformat(),
        urls=ImageSignedUrls(**urls),
    )


def image_storage_keys(image: Image) -> list[str]:
    original = (
        (image.file.name or str(image.file))
        if hasattr(image.file, "name")
        else str(image.file)
    )
    base, _ext = os.path.splitext(original)
    return [
        original,
        *(f"{base}_{suffix}.webp" for suffix in ("thumb", "sm", "md", "lg")),
    ]


def delete_image_record(image: Image) -> int:
    image_id = image.pk
    keys = image_storage_keys(image)
    with transaction.atomic():
        image.delete()

        def delete_objects() -> None:
            for key in keys:
                try:
                    default_storage.delete(key)
                except Exception:
                    logger.exception("images:storage_delete_failed image=%s", image_id)

        transaction.on_commit(delete_objects)
    return image_id
