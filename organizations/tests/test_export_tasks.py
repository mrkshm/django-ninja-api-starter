import io
import zipfile
import json
import pytest
from unittest import mock
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from organizations.models import Organization, Membership
from contacts.models import Contact
from tags.models import Tag, TaggedItem
from images.models import Image
from organizations.export_tasks import export_org_data_task, _serialize_org_data

User = get_user_model()

@pytest.mark.django_db
def test_serialize_org_data_basic(tmp_path, settings):
    # Override storage backend for this test only
    settings.STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    settings.MEDIA_ROOT = tmp_path
    # Setup org, user, contact, tag, image
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group")
    user = User.objects.create(email="admin@example.com", username="admin", first_name="Admin")
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(display_name="John Doe", organization=org, creator=user)
    tag = Tag.objects.create(organization=org, name="VIP", slug="vip")
    TaggedItem.objects.create(tag=tag, content_object=contact)
    image_file = SimpleUploadedFile("test.jpg", b"fakeimgdata", content_type="image/jpeg")
    image = Image.objects.create(file=image_file, organization=org, creator=user)
    # Serialize
    data = _serialize_org_data(org)
    assert data["organization"]["name"] == "Test Org"
    assert data["users"][0]["email"] == "admin@example.com"
    assert data["contacts"][0]["display_name"] == "John Doe"
    assert data["contacts"][0]["tags"] == ["VIP"]
    assert data["tags"][0]["name"] == "VIP"
    assert data["images"][0]["file"] is not None

@pytest.mark.django_db
def test_export_org_data_task_creates_zip_and_emails(tmp_path, settings, monkeypatch):
    # Override storage backend for this test only
    settings.STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    settings.MEDIA_ROOT = tmp_path
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group")
    user = User.objects.create(email="admin@example.com", username="admin", first_name="Admin")
    Membership.objects.create(user=user, organization=org, role="owner")
    image_file = SimpleUploadedFile("test.jpg", b"fakeimgdata", content_type="image/jpeg")
    image = Image.objects.create(file=image_file, organization=org, creator=user)

    # Patch S3 upload and presigned URL
    s3_uploads = {}
    def fake_upload_to_s3(file_bytes, s3_key):
        s3_uploads[s3_key] = file_bytes
    monkeypatch.setattr("organizations.export_tasks._upload_to_s3", fake_upload_to_s3)
    monkeypatch.setattr("organizations.export_tasks._generate_presigned_url", lambda s3_key, expires: f"https://fake-s3/{s3_key}")
    sent_emails = []
    monkeypatch.setattr("organizations.export_tasks.send_email", lambda subject, to, body: sent_emails.append((subject, to, body)))

    result = export_org_data_task(org.id, user.email)
    # Check S3 upload
    assert s3_uploads
    s3_key, zip_bytes = next(iter(s3_uploads.items()))
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zipf:
        assert "data.json" in zipf.namelist()
        assert any(name.startswith("images/") for name in zipf.namelist())
        data = json.loads(zipf.read("data.json"))
        assert data["organization"]["name"] == "Test Org"
    # Check email
    assert sent_emails
    subject, to, body = sent_emails[0]
    assert user.email in to or to == user.email
    assert "Download" in body or "http" in body
