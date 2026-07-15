import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from organizations.models import Organization

User = get_user_model()


@pytest.mark.django_db
def test_generated_identity_retries_after_unique_collision(monkeypatch):
    original_save = User.save
    attempts = 0

    def collide_once(instance, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise IntegrityError("simulated generated-identity collision")
        return original_save(instance, *args, **kwargs)

    monkeypatch.setattr(User, "save", collide_once)

    user = User.objects.create_user(email="collision@example.com", password="pw")

    assert attempts == 2
    assert user.username.startswith("collision_")
    assert Organization.objects.filter(type="personal", creator=user).exists()
