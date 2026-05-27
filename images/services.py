import mimetypes
import os
import logging

from django.conf import settings
from django.utils import timezone

from core.utils.image import resize_images
from core.utils.storage import generate_private_presigned_storage_url
from core.utils.storage import upload_to_storage
from core.utils.utils import generate_upload_filename
from images.models import Image
from images.serializers import build_variant_keys
from images.schemas import ImageSignedUrls, ImageSignedUrlsOut


DEFAULT_SIGNED_URL_TTL_SECONDS = 15 * 60
logger = logging.getLogger(__name__)


def signed_url_ttl_seconds() -> int:
    return int(getattr(settings, "IMAGE_SIGNED_URL_TTL_SECONDS", DEFAULT_SIGNED_URL_TTL_SECONDS))


def image_variant_keys(image: Image) -> dict[str, str]:
    file_name = image.file.name if hasattr(image.file, "name") else str(image.file)
    return build_variant_keys(file_name).model_dump()


def upload_image_file(file, organization, *, creator_id=None) -> Image:
    filename = generate_upload_filename(f"img_{organization.slug[:8]}", file.name)
    data = file.read()
    upload_to_storage(filename, data)
    try:
        variants_bytes = resize_images(data)
        base, _ext = os.path.splitext(filename)
        for key, content in variants_bytes.items():
            upload_to_storage(f"{base}_{key}.webp", content)
    except Exception as e:
        logger.warning(
            "images:variant_generate_failed org=%s file=%s err=%s",
            organization.id,
            filename,
            str(e),
        )
    return Image.objects.create(
        file=filename,
        organization=organization,
        creator_id=creator_id,
        title=file.name,
        description="",
        alt_text="",
    )


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
    expires_at = timezone.now() + timezone.timedelta(seconds=ttl)
    return ImageSignedUrlsOut(
        image_id=image.id,
        expires_at=expires_at.isoformat(),
        urls=ImageSignedUrls(**urls),
    )
