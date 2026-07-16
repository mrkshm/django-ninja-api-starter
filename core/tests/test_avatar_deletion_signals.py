from unittest.mock import patch

import pytest
from django.db import transaction

from accounts.services import delete_user_account
from accounts.tests.utils import create_test_user
from contacts.models import Contact
from organizations.tests.utils import create_test_group


@pytest.mark.django_db
def test_contact_avatar_is_deleted_after_organization_cascade(
    django_capture_on_commit_callbacks,
):
    user = create_test_user(email="contact-avatar-cleanup@example.com")
    organization = create_test_group(
        name="Avatar cleanup", slug="avatar-cleanup", owner=user, creator=user
    )
    Contact.objects.create(
        display_name="Delete me",
        slug="delete-me",
        organization=organization,
        creator=user,
        avatar_path="public/avatars/contacts/contact.webp",
    )

    with patch("core.utils.avatar.delete_avatar_files") as delete_avatar_files:
        with django_capture_on_commit_callbacks(execute=True):
            organization.delete()

    delete_avatar_files.assert_called_once_with("public/avatars/contacts/contact.webp")


@pytest.mark.django_db
def test_contact_avatar_is_preserved_when_delete_rolls_back():
    user = create_test_user(email="contact-avatar-rollback@example.com")
    organization = create_test_group(
        name="Avatar rollback", slug="avatar-rollback", owner=user, creator=user
    )
    contact = Contact.objects.create(
        display_name="Keep me",
        slug="keep-me",
        organization=organization,
        creator=user,
        avatar_path="public/avatars/contacts/keep.webp",
    )
    contact_id = contact.pk

    with patch("core.utils.avatar.delete_avatar_files") as delete_avatar_files:
        with pytest.raises(RuntimeError, match="roll back"):
            with transaction.atomic():
                contact.delete()
                raise RuntimeError("roll back")

    delete_avatar_files.assert_not_called()
    assert Contact.objects.filter(pk=contact_id).exists()


@pytest.mark.django_db
def test_user_avatar_is_deleted_after_account_deletion(
    django_capture_on_commit_callbacks,
):
    user = create_test_user(email="user-avatar-cleanup@example.com")
    user.avatar_path = "public/avatars/users/user.webp"
    user.save(update_fields=["avatar_path", "updated_at"])

    with patch("core.utils.avatar.delete_avatar_files") as delete_avatar_files:
        with django_capture_on_commit_callbacks(execute=True):
            delete_user_account(user)

    delete_avatar_files.assert_called_once_with("public/avatars/users/user.webp")


@pytest.mark.django_db
def test_storage_failure_does_not_undo_committed_contact_deletion(
    django_capture_on_commit_callbacks,
):
    user = create_test_user(email="avatar-storage-failure@example.com")
    organization = create_test_group(
        name="Storage failure", slug="storage-failure", owner=user, creator=user
    )
    contact = Contact.objects.create(
        display_name="Delete despite storage failure",
        slug="delete-despite-storage-failure",
        organization=organization,
        creator=user,
        avatar_path="public/avatars/contacts/failure.webp",
    )
    contact_id = contact.pk

    with patch(
        "core.utils.avatar.delete_avatar_files",
        side_effect=RuntimeError("storage unavailable"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            contact.delete()

    assert not Contact.objects.filter(pk=contact_id).exists()
