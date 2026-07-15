import pytest
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import RequestFactory

from accounts.admin import UserAdmin
from accounts.models import User
from organizations.models import Membership, Organization
from organizations.services import ActiveOwnerRequiredError


def admin_request():
    request = RequestFactory().post("/admin/accounts/user/")
    request.user = User.objects.create_superuser(
        email="platform-admin@example.com", password="pw"
    )
    return request


@pytest.mark.django_db
def test_admin_single_delete_uses_account_lifecycle(
    django_capture_on_commit_callbacks,
):
    user = User.objects.create_user(email="admin-delete@example.com", password="pw")
    avatar_path = default_storage.save(
        "public/avatars/users/admin-delete.webp",
        ContentFile(b"avatar"),
    )
    user.avatar_path = avatar_path
    user.save(update_fields=["avatar_path", "updated_at"])
    personal_org_id = Organization.objects.get(type="personal", creator=user).pk
    user_admin = UserAdmin(User, admin.site)

    with django_capture_on_commit_callbacks(execute=True):
        user_admin.delete_model(admin_request(), user)

    assert not User.objects.filter(pk=user.pk).exists()
    assert not Organization.objects.filter(pk=personal_org_id).exists()
    assert not default_storage.exists(avatar_path)


@pytest.mark.django_db
def test_admin_single_delete_rejects_last_group_owner():
    user = User.objects.create_user(email="last-owner@example.com", password="pw")
    organization = Organization.objects.create(
        name="Owned group", slug="owned-group", type="group"
    )
    Membership.objects.create(user=user, organization=organization, role="owner")
    user_admin = UserAdmin(User, admin.site)

    with pytest.raises(ActiveOwnerRequiredError, match="Promote another"):
        user_admin.delete_model(admin_request(), user)

    assert User.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_admin_bulk_user_deletion_is_disabled():
    user = User.objects.create_user(email="bulk-delete@example.com", password="pw")
    user_admin = UserAdmin(User, admin.site)

    with pytest.raises(PermissionDenied, match="Bulk user deletion"):
        user_admin.delete_queryset(admin_request(), User.objects.filter(pk=user.pk))

    assert User.objects.filter(pk=user.pk).exists()
