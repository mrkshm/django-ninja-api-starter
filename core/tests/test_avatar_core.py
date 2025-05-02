import pytest
from unittest.mock import patch
from types import SimpleNamespace
from core.utils.avatar import delete_existing_avatar

@patch('django.core.files.storage.default_storage.delete')
def test_delete_existing_avatar_calls_storage_delete(mock_delete):
    # Arrange: dummy object with avatar_path
    obj = SimpleNamespace(avatar_path='avatars/foo.webp')
    # Act
    delete_existing_avatar(obj)
    # Assert: should call delete for both small and large avatar
    mock_delete.assert_any_call('avatars/foo.webp')
    mock_delete.assert_any_call('avatars/foo_lg.webp')
    assert mock_delete.call_count == 2

@patch('django.core.files.storage.default_storage.delete')
def test_delete_existing_avatar_no_avatar(mock_delete):
    obj = SimpleNamespace(avatar_path=None)
    delete_existing_avatar(obj)
    mock_delete.assert_not_called()
