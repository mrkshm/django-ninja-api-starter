from unittest.mock import call, patch

import pytest

from images.models import Image
from images.services import delete_image_record
from organizations.models import Organization


@pytest.mark.django_db
def test_delete_image_record_removes_database_row_and_all_storage_variants(
    django_capture_on_commit_callbacks,
):
    organization = Organization.objects.create(name="Delete", slug="delete")
    image = Image.objects.create(
        file="private/images/delete/example.jpg",
        organization=organization,
    )
    expected_id = image.pk

    with (
        patch("images.services.default_storage.delete") as delete,
        django_capture_on_commit_callbacks(execute=True),
    ):
        deleted_id = delete_image_record(image)

    assert deleted_id == expected_id
    assert not Image.objects.filter(pk=deleted_id).exists()
    delete.assert_has_calls(
        [
            call("private/images/delete/example.jpg"),
            call("private/images/delete/example_thumb.webp"),
            call("private/images/delete/example_sm.webp"),
            call("private/images/delete/example_md.webp"),
            call("private/images/delete/example_lg.webp"),
        ],
        any_order=True,
    )
