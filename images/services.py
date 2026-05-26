import mimetypes

from django.conf import settings
from django.utils import timezone

from core.utils.storage import generate_private_presigned_storage_url
from images.models import Image
from images.serializers import build_variant_keys
from images.schemas import ImageSignedUrls, ImageSignedUrlsOut


DEFAULT_SIGNED_URL_TTL_SECONDS = 15 * 60


def signed_url_ttl_seconds() -> int:
    return int(getattr(settings, "IMAGE_SIGNED_URL_TTL_SECONDS", DEFAULT_SIGNED_URL_TTL_SECONDS))


def image_variant_keys(image: Image) -> dict[str, str]:
    file_name = image.file.name if hasattr(image.file, "name") else str(image.file)
    return build_variant_keys(file_name).model_dump()


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
