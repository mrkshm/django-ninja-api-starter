import warnings

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError
from io import BytesIO
from typing import Dict, Tuple, Union


class InvalidImageContent(ValueError):
    pass


def validate_image_content(data: bytes) -> None:
    max_pixels = int(getattr(settings, "UPLOAD_IMAGE_MAX_PIXELS", 40_000_000))
    max_dimension = int(getattr(settings, "UPLOAD_IMAGE_MAX_DIMENSION", 12_000))
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                image.verify()
            with Image.open(BytesIO(data)) as image:
                width, height = image.size
                if width > max_dimension or height > max_dimension:
                    raise InvalidImageContent(
                        "Image dimensions exceed the allowed limit."
                    )
                image.load()
    except InvalidImageContent:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidImageContent("Uploaded file is not a valid image.") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit


def resize_and_save(img, size, quality, format="WEBP"):
    img_copy = img.copy()
    img_copy.thumbnail(size, Image.LANCZOS)
    buf = BytesIO()
    img_copy.save(buf, format=format, quality=quality)
    return buf.getvalue()


def resize_avatar_images(
    image_input: Union[bytes, BytesIO, Image.Image],
    small_size: Tuple[int, int] = (160, 160),
    large_size: Tuple[int, int] = (600, 600),
    format: str = "WEBP",
) -> Tuple[bytes, bytes]:
    """
    Resize an image to small and large avatar sizes (default 160x160, 600x600) in WebP format.
    Returns (small_image_bytes, large_image_bytes).
    Accepts bytes, BytesIO, or PIL.Image.Image as input.
    """
    image: Image.Image
    if isinstance(image_input, bytes):
        validate_image_content(image_input)
        image = Image.open(BytesIO(image_input))
    elif isinstance(image_input, BytesIO):
        image = Image.open(image_input)
    elif isinstance(image_input, Image.Image):
        image = image_input
    else:
        raise TypeError("Unsupported image_input type")

    image = ImageOps.exif_transpose(image)
    # Ensure image is RGBA or RGB for webp
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")

    small_bytes = resize_and_save(image, small_size, 65, format=format)
    large_bytes = resize_and_save(image, large_size, 85, format=format)
    return small_bytes, large_bytes


def normalize_image_bytes(data: bytes) -> bytes:
    """Decode, orient, strip metadata, and encode an upload as WebP."""
    validate_image_content(data)
    with Image.open(BytesIO(data)) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        max_dimension = int(getattr(settings, "UPLOAD_IMAGE_MAX_DIMENSION", 12_000))
        return resize_and_save(
            normalized,
            (max_dimension, max_dimension),
            90,
            format="WEBP",
        )


def resize_images(
    image_input: Union[bytes, BytesIO, Image.Image],
) -> Dict[str, bytes]:
    """
    Resize an image to four versions according to project specs:
      - Thumbnail: 160x160, 65% quality
      - Small: 640x640, 80% quality
      - Medium: 1024x1024, 85% quality
      - Large: 2048x2048, 85% quality
    Returns a dict with keys: 'thumb', 'sm', 'md', 'lg', each value is bytes (webp).
    Accepts bytes, BytesIO, or PIL.Image.Image as input.
    """
    SIZES = {
        "thumb": ((160, 160), 65),
        "sm": ((640, 640), 80),
        "md": ((1024, 1024), 85),
        "lg": ((2048, 2048), 85),
    }
    image: Image.Image
    if isinstance(image_input, bytes):
        validate_image_content(image_input)
        image = Image.open(BytesIO(image_input))
    elif isinstance(image_input, BytesIO):
        image = Image.open(image_input)
    elif isinstance(image_input, Image.Image):
        image = image_input
    else:
        raise ValueError("Unsupported image input type")
    image = ImageOps.exif_transpose(image).convert("RGB")

    results = {}
    for key, (size, quality) in SIZES.items():
        results[key] = resize_and_save(image, size, quality, format="WEBP")
    return results
