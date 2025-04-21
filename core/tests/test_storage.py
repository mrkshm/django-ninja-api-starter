from core.utils import upload_to_storage, delete_existing_avatar
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
