import os
from unittest.mock import patch

import pytest

from images.services import ImageUploadFailed, upload_image_file
from organizations.models import Organization


@pytest.mark.django_db
def test_database_failure_compensates_all_uploaded_objects():
    organization = Organization.objects.create(name="Acme", slug="acme")

    with (
        patch("images.services.normalize_image_bytes", return_value=b"normalized"),
        patch(
            "images.services.resize_images",
            return_value={"thumb": b"thumb", "sm": b"small"},
        ),
        patch("images.services.upload_to_storage") as upload,
        patch("images.services.delete_storage_keys") as delete,
        patch("images.services.Image.objects.create", side_effect=RuntimeError("db")),
    ):
        with pytest.raises(ImageUploadFailed):
            upload_image_file(
                b"input", organization, original_name="photo.png", creator_id=None
            )

    uploaded_keys = [call.args[0] for call in upload.call_args_list]
    delete.assert_called_with(uploaded_keys)
    assert len(uploaded_keys) == 3
    assert all(str(organization.pk) in key for key in uploaded_keys)


@pytest.mark.django_db
def test_successful_upload_persists_image_after_all_variants():
    organization = Organization.objects.create(name="Upload", slug="upload")
    variants = {
        "thumb": b"thumb",
        "sm": b"small",
        "md": b"medium",
        "lg": b"large",
    }

    with (
        patch("images.services.normalize_image_bytes", return_value=b"normalized"),
        patch("images.services.resize_images", return_value=variants),
        patch("images.services.upload_to_storage") as upload,
    ):
        image = upload_image_file(
            b"input",
            organization,
            original_name="photo.png",
            creator_id=None,
        )

    original_key = str(image.file)
    base, _extension = os.path.splitext(original_key)
    assert image.organization == organization
    assert image.visibility == "private"
    assert image.title == "photo.png"
    assert [call.args[0] for call in upload.call_args_list] == [
        original_key,
        f"{base}_thumb.webp",
        f"{base}_sm.webp",
        f"{base}_md.webp",
        f"{base}_lg.webp",
    ]
