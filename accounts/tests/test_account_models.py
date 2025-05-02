import pytest
from django.core.cache import cache
from accounts.models import User, PendingEmailChange, PendingPasswordReset
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.auth.models import PermissionsMixin

@pytest.mark.django_db
def test_create_superuser_sets_flags():
    UserModel = get_user_model()
    superuser = UserModel.objects.create_superuser(email="admin@example.com", password="pw1234")
    assert superuser.is_staff is True
    assert superuser.is_superuser is True
    assert superuser.check_password("pw1234")

@pytest.mark.django_db
def test_pending_email_change_str():
    user = User.objects.create_user(email="test@example.com", password="pw")
    now = timezone.now()
    obj = PendingEmailChange.objects.create(user=user, new_email="new@example.com", token="tok", expires_at=now)
    s = str(obj)
    assert "PendingEmailChange(user=" in s and "new_email=new@example.com" in s

@pytest.mark.django_db
def test_pending_password_reset_str():
    user = User.objects.create_user(email="reset@example.com", password="pw")
    now = timezone.now()
    obj = PendingPasswordReset.objects.create(user=user, token="tok", expires_at=now)
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
def test_get_user_permissions_caching(monkeypatch):
    user = User.objects.create_user(email="perm@example.com", password="pw")
    cache_key = f'user_permissions_{user.id}'
    cache.delete(cache_key)
    called = {}

    original = PermissionsMixin.get_user_permissions

    def fake_super_get_user_permissions(self):
        called['called'] = called.get('called', 0) + 1
        return {"foo"}

    monkeypatch.setattr(PermissionsMixin, "get_user_permissions", fake_super_get_user_permissions)

    # First call: should call the patched super method and set cache
    perms = user.get_user_permissions()
    assert perms == {"foo"}
    assert called['called'] == 1

    # Second call: should use cache, not call the patched method again
    called['called'] = 0
    perms2 = user.get_user_permissions()
    assert perms2 == {"foo"}
    assert called['called'] == 0  # Should not call the patched method, uses cache

    # Restore original
    monkeypatch.setattr(PermissionsMixin, "get_user_permissions", original)
