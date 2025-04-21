from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

def upload_to_storage(filename, content, content_type="image/webp", storage=None):
    """
    Uploads a file to the given storage (default: default_storage).
    - filename: the key/path in storage (e.g. 'avatars/avatar_xxx.webp')
    - content: bytes or file-like object
    - content_type: MIME type (default: image/webp)
    Returns the storage URL for the uploaded file.
    """
    storage = storage or default_storage
    file = ContentFile(content)
    storage.save(filename, file)
    return storage.url(filename)
