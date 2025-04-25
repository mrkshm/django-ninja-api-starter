from PIL import Image
from io import BytesIO
from typing import Tuple, Union, Dict

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
    if isinstance(image_input, bytes):
        image = Image.open(BytesIO(image_input))
    elif isinstance(image_input, BytesIO):
        image = Image.open(image_input)
    elif isinstance(image_input, Image.Image):
        image = image_input
    else:
        raise TypeError("Unsupported image_input type")

    # Ensure image is RGBA or RGB for webp
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")

    small_bytes = resize_and_save(image, small_size, 65, format=format)
    large_bytes = resize_and_save(image, large_size, 85, format=format)
    return small_bytes, large_bytes

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
        'thumb':  ((160, 160), 65),
        'sm':     ((640, 640), 80),
        'md':     ((1024, 1024), 85),
        'lg':     ((2048, 2048), 85),
    }
    if isinstance(image_input, bytes):
        image = Image.open(BytesIO(image_input))
    elif isinstance(image_input, BytesIO):
        image = Image.open(image_input)
    elif isinstance(image_input, Image.Image):
        image = image_input
    else:
        raise ValueError("Unsupported image input type")
    image = image.convert("RGB")

    results = {}
    for key, (size, quality) in SIZES.items():
        results[key] = resize_and_save(image, size, quality, format="WEBP")
    return results
