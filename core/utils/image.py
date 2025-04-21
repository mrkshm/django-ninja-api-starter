from PIL import Image
from io import BytesIO
from typing import Tuple, Union

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

    # Resize and save to bytes
    def resize_and_save(img, size, quality):
        resized = img.copy()
        resized.thumbnail(size, Image.LANCZOS)
        out = BytesIO()
        resized.save(out, format=format, quality=quality)
        return out.getvalue()

    small_bytes = resize_and_save(image, small_size, 65)
    large_bytes = resize_and_save(image, large_size, 85)
    return small_bytes, large_bytes
