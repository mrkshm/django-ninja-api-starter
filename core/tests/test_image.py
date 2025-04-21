from core.utils import resize_avatar_images
from PIL import Image
from io import BytesIO

def test_resize_avatar_images_basic():
    # Create a red 1000x1000 image in memory
    img = Image.new("RGB", (1000, 1000), color="red")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    original_bytes = buf.read()

    small, large = resize_avatar_images(original_bytes)

    # Check that outputs are not empty
    assert len(small) > 0
    assert len(large) > 0

    # Check that the images are the correct size
    s_img = Image.open(BytesIO(small))
    l_img = Image.open(BytesIO(large))
    assert s_img.size == (160, 160)
    assert l_img.size == (600, 600)
    assert s_img.format == "WEBP"
    assert l_img.format == "WEBP"

    # Check that the small image is smaller in bytes than the large one
    assert len(small) < len(large)

def test_resize_avatar_images_non_square():
    # Create a 1200x600 blue image (non-square, landscape)
    img = Image.new("RGB", (1200, 600), color="blue")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    original_bytes = buf.read()

    small, large = resize_avatar_images(original_bytes)

    # Check that outputs are not empty
    assert len(small) > 0
    assert len(large) > 0

    # Check that the images are the correct size (should fit within 160x160 and 600x600)
    s_img = Image.open(BytesIO(small))
    l_img = Image.open(BytesIO(large))
    assert s_img.size[0] <= 160 and s_img.size[1] <= 160
    assert l_img.size[0] <= 600 and l_img.size[1] <= 600
    assert s_img.format == "WEBP"
    assert l_img.format == "WEBP"

    # Aspect ratio should be preserved
    orig_ratio = 1200 / 600
    small_ratio = s_img.size[0] / s_img.size[1]
    large_ratio = l_img.size[0] / l_img.size[1]
    assert abs(small_ratio - orig_ratio) < 0.01
    assert abs(large_ratio - orig_ratio) < 0.01
