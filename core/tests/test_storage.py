from core.utils import delete_existing_avatar, generate_presigned_storage_url, upload_to_storage
from unittest.mock import patch, MagicMock
import types

def test_upload_to_storage_calls_save_and_url():
    content = b"test-bytes"
    filename = "avatars/test.webp"
    fake_url = "https://fake-bucket/avatars/test.webp"

    with patch("django.core.files.storage.default_storage.save") as mock_save, \
         patch("django.core.files.storage.default_storage.url") as mock_url:
        mock_save.return_value = filename
        mock_url.return_value = fake_url

        url = upload_to_storage(filename, content)

        mock_save.assert_called_once()
        mock_url.assert_called_once_with(filename)
        assert url == fake_url

class DummyProfile:
    def __init__(self, avatar):
        self.avatar = avatar

class DummyUser:
    def __init__(self, avatar):
        self.profile = DummyProfile(avatar)
        self.avatar_path = avatar

def test_delete_existing_avatar_calls_delete_for_both_sizes():
    user = DummyUser("avatars/avatar123.webp")
    with patch("django.core.files.storage.default_storage.delete") as mock_delete:
        delete_existing_avatar(user)
        # Should delete both small and large
        mock_delete.assert_any_call("avatars/avatar123.webp")
        mock_delete.assert_any_call("avatars/avatar123_lg.webp")
        assert mock_delete.call_count == 2

def test_delete_existing_avatar_no_avatar():
    user = DummyUser(None)
    with patch("django.core.files.storage.default_storage.delete") as mock_delete:
        delete_existing_avatar(user)
        mock_delete.assert_not_called()


def test_generate_presigned_storage_url_builds_s3_request(monkeypatch):
    called = {}

    class DummyClient:
        def generate_presigned_url(self, operation, Params, ExpiresIn):
            called["operation"] = operation
            called["params"] = Params
            called["expires_in"] = ExpiresIn
            return "https://signed.example/avatar.webp"

    def fake_client(service, **kwargs):
        called["service"] = service
        called["kwargs"] = kwargs
        return DummyClient()

    monkeypatch.setattr("core.utils.storage.boto3.client", fake_client)
    generate_presigned_storage_url(
        "avatars/avatar.webp",
        expires_in=120,
        content_type="image/webp",
        cache_control="public, max-age=120",
        storage_options={
            "endpoint_url": "https://r2.example",
            "access_key": "access",
            "secret_key": "secret",
            "region_name": "auto",
            "bucket_name": "bucket",
        },
    )

    assert called["service"] == "s3"
    assert called["kwargs"]["endpoint_url"] == "https://r2.example"
    assert called["params"] == {
        "Bucket": "bucket",
        "Key": "avatars/avatar.webp",
        "ResponseContentType": "image/webp",
        "ResponseCacheControl": "public, max-age=120",
    }
    assert called["expires_in"] == 120
