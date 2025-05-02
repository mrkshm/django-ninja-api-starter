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
from organizations.export_tasks import export_org_data_task, _serialize_org_data, _upload_to_s3, _generate_presigned_url

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

def test_upload_to_s3_success(monkeypatch):
    fake_s3 = mock.Mock()
    monkeypatch.setattr("organizations.export_tasks.boto3.client", lambda service: fake_s3)
    monkeypatch.setattr("organizations.export_tasks.get_export_bucket", lambda: "mybucket")
    file_bytes = b"abc"
    s3_key = "some/key.zip"
    _upload_to_s3(file_bytes, s3_key)
    fake_s3.upload_fileobj.assert_called_once()
    args, kwargs = fake_s3.upload_fileobj.call_args
    assert isinstance(args[0], io.BytesIO)
    assert args[1] == "mybucket"
    assert args[2] == s3_key

def test_upload_to_s3_no_bucket(monkeypatch):
    monkeypatch.setattr("organizations.export_tasks.boto3.client", lambda service: mock.Mock())
    monkeypatch.setattr("organizations.export_tasks.get_export_bucket", lambda: None)
    with pytest.raises(RuntimeError, match="No S3 bucket configured for exports"):
        _upload_to_s3(b"abc", "some/key.zip")

def test_generate_presigned_url_success(monkeypatch):
    fake_s3 = mock.Mock()
    fake_s3.generate_presigned_url.return_value = "https://presigned.url"
    monkeypatch.setattr("organizations.export_tasks.boto3.client", lambda service: fake_s3)
    monkeypatch.setattr("organizations.export_tasks.get_export_bucket", lambda: "mybucket")
    url = _generate_presigned_url("some/key.zip", expires=1234)
    fake_s3.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "mybucket", "Key": "some/key.zip"},
        ExpiresIn=1234,
    )
    assert url == "https://presigned.url"

def test_generate_presigned_url_no_bucket(monkeypatch):
    monkeypatch.setattr("organizations.export_tasks.boto3.client", lambda service: mock.Mock())
    monkeypatch.setattr("organizations.export_tasks.get_export_bucket", lambda: None)
    with pytest.raises(RuntimeError, match="No S3 bucket configured for exports"):
        _generate_presigned_url("some/key.zip")

def test_generate_presigned_url_clienterror(monkeypatch):
    fake_s3 = mock.Mock()
    def raise_client_error(*a, **k):
        from botocore.exceptions import ClientError
        raise ClientError({}, "generate_presigned_url")
    fake_s3.generate_presigned_url.side_effect = raise_client_error
    monkeypatch.setattr("organizations.export_tasks.boto3.client", lambda service: fake_s3)
    monkeypatch.setattr("organizations.export_tasks.get_export_bucket", lambda: "mybucket")
    url = _generate_presigned_url("some/key.zip")
    assert url is None

def test_get_export_bucket(settings):
    # Only EXPORT_BUCKET
    settings.EXPORT_BUCKET = "export-bucket"
    if hasattr(settings, "AWS_STORAGE_BUCKET_NAME"):
        del settings.AWS_STORAGE_BUCKET_NAME
    from organizations.export_tasks import get_export_bucket
    assert get_export_bucket() == "export-bucket"
    # Only AWS_STORAGE_BUCKET_NAME
    del settings.EXPORT_BUCKET
    settings.AWS_STORAGE_BUCKET_NAME = "aws-bucket"
    assert get_export_bucket() == "aws-bucket"
    # Neither set
    del settings.AWS_STORAGE_BUCKET_NAME
    assert get_export_bucket() is None
