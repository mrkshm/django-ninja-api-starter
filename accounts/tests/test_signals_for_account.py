import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from unittest.mock import patch

User = get_user_model()

@pytest.mark.django_db
def test_invalidate_user_permissions_cache_on_permission_change():
    user = User.objects.create_user(email="sigtest@example.com", password="pw")
    perm = Permission.objects.first()
    with patch("accounts.signals.cache.delete") as mock_delete:
        user.user_permissions.add(perm)
        mock_delete.assert_called_with(f"user_permissions_{user.id}")

@pytest.mark.django_db
def test_invalidate_user_permissions_cache_on_group_change():
    user = User.objects.create_user(email="sigtest2@example.com", password="pw")
    group = Group.objects.create(name="testgroup")
    with patch("accounts.signals.cache.delete") as mock_delete:
        user.groups.add(group)
        mock_delete.assert_called_with(f"user_permissions_{user.id}")