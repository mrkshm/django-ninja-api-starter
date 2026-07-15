import pytest

from core.utils.uploads import UploadTooLarge, read_uploaded_file_bounded


class NeverReadOversizedUpload:
    size = 11
    file = None

    def read(self, _size):
        raise AssertionError("oversized upload must be rejected before reading")


class UndeclaredOversizedUpload:
    size = None
    file = None

    def read(self, size):
        return b"x" * size


def test_declared_oversized_upload_is_not_read():
    with pytest.raises(UploadTooLarge):
        read_uploaded_file_bounded(NeverReadOversizedUpload(), max_bytes=10)


def test_bounded_read_rejects_when_declared_size_is_missing():
    with pytest.raises(UploadTooLarge):
        read_uploaded_file_bounded(UndeclaredOversizedUpload(), max_bytes=10)
