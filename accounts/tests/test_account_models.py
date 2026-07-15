import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.utils import timezone

from accounts.models import PendingEmailChange, PendingPasswordReset, User
from accounts.tokens import hash_token


@pytest.mark.django_db
def test_create_superuser_sets_flags():
    UserModel = get_user_model()
    superuser = UserModel.objects.create_superuser(
        email="admin@example.com", password="pw1234"
    )
    assert superuser.is_staff is True
    assert superuser.is_superuser is True
    assert superuser.check_password("pw1234")


@pytest.mark.django_db
def test_pending_email_change_str():
    user = User.objects.create_user(email="test@example.com", password="pw")
    now = timezone.now()
    obj = PendingEmailChange.objects.create(
        user=user,
        new_email="new@example.com",
        auth_version=user.auth_version,
        token=hash_token("tok"),
        expires_at=now,
    )
    s = str(obj)
    assert "PendingEmailChange(user=" in s and "new_email=new@example.com" in s


@pytest.mark.django_db
def test_pending_password_reset_str():
    user = User.objects.create_user(email="reset@example.com", password="pw")
    now = timezone.now()
    obj = PendingPasswordReset.objects.create(
        user=user, token=hash_token("tok"), expires_at=now
    )
    s = str(obj)
    assert "PendingPasswordReset(user=" in s


@pytest.mark.django_db
def test_user_str():
    user = User.objects.create_user(email="foo@example.com", password="pw")
    assert str(user) == "foo@example.com"


@pytest.mark.django_db
def test_create_user_requires_email():
    UserModel = get_user_model()
    with pytest.raises(ValueError) as exc:
        UserModel.objects.create_user(email=None, password="pw1234")
    assert "Email field must be set" in str(exc.value)


@pytest.mark.django_db
def test_direct_permission_changes_are_visible_to_fresh_user_instances():
    user = User.objects.create_user(email="perm@example.com", password="pw")
    permission = Permission.objects.first()
    assert permission is not None
    permission_name = f"{permission.content_type.app_label}.{permission.codename}"

    user.user_permissions.add(permission)
    assert permission_name in User.objects.get(pk=user.pk).get_user_permissions()

    user.user_permissions.remove(permission)
    assert permission_name not in User.objects.get(pk=user.pk).get_user_permissions()


@pytest.mark.django_db
def test_group_permission_changes_are_visible_to_fresh_user_instances():
    user = User.objects.create_user(email="group-perm@example.com", password="pw")
    permission = Permission.objects.first()
    assert permission is not None
    permission_name = f"{permission.content_type.app_label}.{permission.codename}"
    group = Group.objects.create(name="permission-test-group")
    group.permissions.add(permission)

    user.groups.add(group)
    assert permission_name in User.objects.get(pk=user.pk).get_group_permissions()

    user.groups.remove(group)
    assert permission_name not in User.objects.get(pk=user.pk).get_group_permissions()
