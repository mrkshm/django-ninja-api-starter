from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import User
from accounts.services import issue_token_pair
from organizations.models import Membership, Organization


@pytest.fixture
def upload_route_context():
    user = User.objects.create_user(email="upload-limits@example.com", password="pw")
    organization = Organization.objects.create(
        name="Upload Limits", slug="upload-limits", type="group"
    )
    Membership.objects.create(user=user, organization=organization, role="owner")
    access, _refresh = issue_token_pair(user)
    headers = {"Authorization": f"Bearer {access}"}
    return organization, headers


def uploaded_file(name: str, content: bytes, content_type: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type=content_type)


@pytest.mark.django_db
def test_single_upload_rejects_oversize_multipart_before_processing(
    api_client, upload_route_context, settings
):
    organization, headers = upload_route_context
    settings.UPLOAD_IMAGE_MAX_BYTES = 5

    with patch("images.api.uploads.upload_image_file") as upload:
        response = api_client.post(
            f"/orgs/{organization.slug}/images/",
            data={},
            FILES={"file": uploaded_file("large.png", b"x" * 6, "image/png")},
            headers=headers,
        )

    assert response.status_code == 400
    assert "File too large" in response.json()["detail"]
    upload.assert_not_called()


@pytest.mark.django_db
def test_single_upload_rejects_invalid_multipart_mime(
    api_client, upload_route_context, settings
):
    organization, headers = upload_route_context
    settings.UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES = ("image/",)

    with patch("images.api.uploads.upload_image_file") as upload:
        response = api_client.post(
            f"/orgs/{organization.slug}/images/",
            data={},
            FILES={
                "file": uploaded_file("document.pdf", b"%PDF-1.4", "application/pdf")
            },
            headers=headers,
        )

    assert response.status_code == 400
    assert "Invalid file type" in response.json()["detail"]
    upload.assert_not_called()


@pytest.mark.django_db
def test_bulk_upload_rejects_oversize_multipart_before_processing(
    api_client, upload_route_context, settings
):
    organization, headers = upload_route_context
    settings.UPLOAD_IMAGE_MAX_BYTES = 6
    files = [
        uploaded_file("large.jpg", b"x" * 7, "image/jpeg"),
        uploaded_file("small.jpg", b"abcd", "image/jpeg"),
    ]

    with patch("images.api.uploads.upload_image_file") as upload:
        response = api_client.post(
            f"/orgs/{organization.slug}/bulk-upload/",
            data={},
            FILES={"files": files},
            headers=headers,
        )

    assert response.status_code == 400
    assert "per-file size" in response.json()["detail"]
    upload.assert_not_called()


@pytest.mark.django_db
def test_bulk_upload_rejects_multipart_file_count_before_processing(
    api_client, upload_route_context, settings
):
    organization, headers = upload_route_context
    settings.UPLOAD_IMAGE_MAX_FILES_PER_REQUEST = 1
    files = [
        uploaded_file("first.jpg", b"a", "image/jpeg"),
        uploaded_file("second.jpg", b"b", "image/jpeg"),
    ]

    with patch("images.api.uploads.upload_image_file") as upload:
        response = api_client.post(
            f"/orgs/{organization.slug}/bulk-upload/",
            data={},
            FILES={"files": files},
            headers=headers,
        )

    assert response.status_code == 400
    assert "at most 1" in response.json()["detail"]
    upload.assert_not_called()


@pytest.mark.django_db
def test_bulk_upload_rejects_multipart_aggregate_size_before_processing(
    api_client, upload_route_context, settings
):
    organization, headers = upload_route_context
    settings.UPLOAD_IMAGE_MAX_TOTAL_BYTES = 5
    files = [
        uploaded_file("first.jpg", b"aaa", "image/jpeg"),
        uploaded_file("second.jpg", b"bbb", "image/jpeg"),
    ]

    with patch("images.api.uploads.upload_image_file") as upload:
        response = api_client.post(
            f"/orgs/{organization.slug}/bulk-upload/",
            data={},
            FILES={"files": files},
            headers=headers,
        )

    assert response.status_code == 400
    assert "aggregate size" in response.json()["detail"]
    upload.assert_not_called()
