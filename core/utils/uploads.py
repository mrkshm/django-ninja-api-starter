class UploadTooLarge(ValueError):
    pass


def read_uploaded_file_bounded(uploaded_file, *, max_bytes: int) -> bytes:
    """Read at most max_bytes without copying an oversized upload into memory."""
    declared_size = getattr(uploaded_file, "size", None)
    if declared_size is not None and declared_size > max_bytes:
        raise UploadTooLarge
    underlying = getattr(uploaded_file, "file", None)
    if underlying is not None:
        underlying.seek(0)
    data = uploaded_file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UploadTooLarge
    return data
