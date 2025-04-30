import os
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from images.models import Image, PolymorphicImageRelation
from images.tasks import cleanup_orphaned_images
from organizations.models import Organization
from accounts.models import User

@pytest.mark.django_db
def test_cleanup_orphaned_images(tmp_path, settings):
    # Override storage backend for this test only
    settings.STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    # Use temp dir for media
    settings.MEDIA_ROOT = tmp_path
    org = Organization.objects.create(name="Test Org")
    user = User.objects.create_user(email="test@example.com", password="pw")
    # Create orphaned image
    img_file = SimpleUploadedFile("img.jpg", b"fakeimgdata", content_type="image/jpeg")
    image = Image.objects.create(file=img_file, organization=org, creator=user)
    print("STORAGE BACKEND:", image.file.storage.__class__)
    # Simulate variants
    base_path = image.file.path
    for suffix in ["_thumb", "_sm", "_md", "_lg"]:
        variant_path = base_path.replace(".jpg", f"{suffix}.webp")
        with open(variant_path, "wb") as f:
            f.write(b"variantdata")
    # Create image with relation (should NOT be deleted)
    img_file2 = SimpleUploadedFile("img2.jpg", b"fakeimgdata2", content_type="image/jpeg")
    image2 = Image.objects.create(file=img_file2, organization=org, creator=user)
    PolymorphicImageRelation.objects.create(image=image2, content_object=org)
    # Run cleanup
    cleanup_orphaned_images()
    # Orphaned image and all variants should be gone
    assert not Image.objects.filter(pk=image.pk).exists()
    assert not os.path.exists(base_path)
    for suffix in ["_thumb", "_sm", "_md", "_lg"]:
        assert not os.path.exists(base_path.replace(".jpg", f"{suffix}.webp"))
    # Related image should remain
    assert Image.objects.filter(pk=image2.pk).exists()
    assert os.path.exists(image2.file.path)
