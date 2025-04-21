import os
from django.core.files.storage import default_storage

def delete_existing_avatar(obj):
    """
    Deletes both small and large avatar files for the given object from storage.
    Expects the object to have an 'avatar_path' attribute.
    """
    avatar_filename = getattr(obj, "avatar_path", None)
    if not avatar_filename:
        return

    base, ext = os.path.splitext(avatar_filename)
    large_filename = f"{base}_lg{ext}"
    default_storage.delete(avatar_filename)
    default_storage.delete(large_filename)