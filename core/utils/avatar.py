import logging
import os

from django.db import transaction

from core.utils.storage import delete_from_public_storage

logger = logging.getLogger(__name__)


def delete_existing_avatar(obj):
    """
    Deletes both small and large avatar files for the given object from storage.
    Expects the object to have an 'avatar_path' attribute.
    """
    avatar_filename = getattr(obj, "avatar_path", None)
    if not avatar_filename:
        return

    delete_avatar_files(avatar_filename)


def delete_avatar_files(avatar_filename: str) -> None:
    base, ext = os.path.splitext(avatar_filename)
    large_filename = f"{base}_lg{ext}"
    delete_from_public_storage(avatar_filename)
    delete_from_public_storage(large_filename)


def schedule_avatar_file_deletion(avatar_filename: str | None) -> None:
    if not avatar_filename:
        return

    def delete_after_commit() -> None:
        try:
            delete_avatar_files(avatar_filename)
        except Exception:
            logger.exception(
                "avatar:delete_failed path=%s",
                avatar_filename,
            )

    transaction.on_commit(delete_after_commit)
