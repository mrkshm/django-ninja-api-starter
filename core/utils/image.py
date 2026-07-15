import warnings
from io import BytesIO
from typing import Dict, Tuple, Union

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError


class InvalidImageContent(ValueError):
    pass


def _validate_image_dimensions(image: Image.Image) -> None:
    max_pixels = int(getattr(settings, "UPLOAD_IMAGE_MAX_PIXELS", 40_000_000))
    max_dimension = int(getattr(settings, "UPLOAD_IMAGE_MAX_DIMENSION", 12_000))
    width, height = image.size
    if (
        width <= 0
        or height <= 0
        or width > max_dimension
        or height > max_dimension
        or width * height > max_pixels
    ):
        raise InvalidImageContent("Image dimensions exceed the allowed limit.")


def _load_validated_image(image: Image.Image) -> None:
    _validate_image_dimensions(image)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        image.load()


def validate_image_content(data: bytes) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                _validate_image_dimensions(image)
                image.verify()
            with Image.open(BytesIO(data)) as image:
                _load_validated_image(image)
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


def _coerce_validated_image(
    image_input: Union[bytes, BytesIO, Image.Image],
) -> tuple[Image.Image, bool]:
    if isinstance(image_input, bytes):
        validate_image_content(image_input)
        return Image.open(BytesIO(image_input)), True
    if isinstance(image_input, BytesIO):
        data = image_input.getvalue()
        validate_image_content(data)
        return Image.open(BytesIO(data)), True
    if isinstance(image_input, Image.Image):
        try:
            _load_validated_image(image_input)
        except (
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise InvalidImageContent("Uploaded file is not a valid image.") from exc
        return image_input, False
    raise TypeError("Unsupported image_input type")


def resize_and_save(img, size, quality, format="WEBP"):
    img_copy = img.copy()
    img_copy.thumbnail(size, Image.Resampling.LANCZOS)
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
    source, should_close = _coerce_validated_image(image_input)
    try:
        image = ImageOps.exif_transpose(source)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")
        small_bytes = resize_and_save(image, small_size, 65, format=format)
        large_bytes = resize_and_save(image, large_size, 85, format=format)
        return small_bytes, large_bytes
    finally:
        if should_close:
            source.close()


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
    try:
        source, should_close = _coerce_validated_image(image_input)
    except TypeError as exc:
        raise ValueError("Unsupported image input type") from exc
    try:
        image = ImageOps.exif_transpose(source).convert("RGB")
        results = {}
        for key, (size, quality) in SIZES.items():
            results[key] = resize_and_save(image, size, quality, format="WEBP")
        return results
    finally:
        if should_close:
            source.close()
