import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.contrib.auth.models import Permission, Group
from django.contrib.contenttypes.models import ContentType

User = get_user_model()

@pytest.mark.django_db
def test_user_permissions_cache_invalidation():
    user = User.objects.create_user(email="test2@example.com", password="pw")
    user.is_staff = True
    user.save()
    ct = ContentType.objects.get_for_model(User)
    perms = Permission.objects.filter(content_type=ct)
    perm = perms.first()
    assert perm is not None, "No permission found for User model"
    perm_str = f"{perm.content_type.app_label}.{perm.codename}"

    perms_before = user.get_all_permissions()
    user.user_permissions.add(perm)
    perms_after = user.get_all_permissions()
    print("Permissions after type:", type(perms_after), perms_after)
    assert perm_str not in perms_before
    assert perm_str in perms_after
    user.user_permissions.remove(perm)
    perms_after_remove = user.get_all_permissions()
    assert perm_str not in perms_after_remove

@pytest.mark.django_db
def test_user_group_permissions_cache_invalidation():
    user = User.objects.create_user(email="test3@example.com", password="pw")
    user.is_staff = True
    user.save()
    group = Group.objects.create(name="TestGroup")
    ct = ContentType.objects.get_for_model(User)
    perms = Permission.objects.filter(content_type=ct)
    perm = perms.first()
    assert perm is not None, "No permission found for User model"
    perm_str = f"{perm.content_type.app_label}.{perm.codename}"

    perms_before = user.get_all_permissions()
    group.permissions.add(perm)
    user.groups.add(group)
    perms_after = user.get_all_permissions()
    print("Permissions after type:", type(perms_after), perms_after)
    assert perm_str not in perms_before
    assert perm_str in perms_after
    user.groups.remove(group)
    perms_after_remove = user.get_all_permissions()
    assert perm_str not in perms_after_remove
