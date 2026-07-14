import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
import pytest

from accounts.models import PendingPasswordReset
from accounts.tests.utils import create_test_user
from accounts.tokens import hash_token

User = get_user_model()


@pytest.mark.django_db
def test_password_reset_request_valid_email(settings, api_client):
    user = create_test_user(email="user@example.com", password="pass1234")
    url = "/auth/password-reset/request"
    data = {"email": "user@example.com"}
    with patch("accounts.services.send_email_task.delay") as mock_send_email:
        response = api_client.post(url, json=data)
        assert response.status_code == 200
        assert "detail" in response.json()
        assert "reset link has been sent" in response.json()["detail"]
        # A PendingPasswordReset should be created
        assert PendingPasswordReset.objects.filter(user=user).exists()
        assert len(PendingPasswordReset.objects.get(user=user).token) == 64
        # Email should be sent
        assert mock_send_email.called

@pytest.mark.django_db
def test_password_reset_request_invalid_email_format(api_client):
    url = "/auth/password-reset/request"
    data = {"email": "not-an-email"}
    response = api_client.post(url, json=data)
    assert response.status_code == 200
    assert "reset link has been sent" in response.json()["detail"]

@pytest.mark.django_db
def test_password_reset_request_nonexistent_email(api_client):
    url = "/auth/password-reset/request"
    data = {"email": "nobody@example.com"}
    response = api_client.post(url, json=data)
    assert response.status_code == 200
    assert "reset link has been sent" in response.json()["detail"]

@pytest.mark.django_db
def test_password_reset_request_deletes_previous(settings, api_client):
    user = create_test_user(email="user2@example.com", password="pass1234")
    expires_at = timezone.now() + datetime.timedelta(hours=2)
    PendingPasswordReset.objects.create(user=user, token="oldtoken", expires_at=expires_at)
    url = "/auth/password-reset/request"
    data = {"email": "user2@example.com"}
    with patch("accounts.services.send_email_task.delay"):
        response = api_client.post(url, json=data)
    assert response.status_code == 200
    # Only one PendingPasswordReset should exist now
    assert PendingPasswordReset.objects.filter(user=user).count() == 1

@pytest.mark.django_db
def test_password_reset_request_email_send_failure(monkeypatch, api_client):
    user = create_test_user(email="failmail@example.com", password="pw")
    url = "/auth/password-reset/request"
    data = {"email": "failmail@example.com"}
    # Patch send_email_task.delay to raise an exception
    from core import tasks as core_tasks
    def fail_send_email_task(*args, **kwargs):
        raise Exception("Simulated email failure")
    monkeypatch.setattr(core_tasks.send_email_task, "delay", fail_send_email_task)
    response = api_client.post(url, json=data)
    # Should still return 200 and generic message
    assert response.status_code == 200
    assert "reset link has been sent" in response.json()["detail"]

@pytest.mark.django_db
def test_password_reset_confirm_success(api_client):
    user = create_test_user(email="resetme@example.com", password="oldpassword")
    # Create a valid PendingPasswordReset
    from django.utils import timezone
    import secrets
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timezone.timedelta(hours=2)
    from accounts.models import PendingPasswordReset
    PendingPasswordReset.objects.create(user=user, token=hash_token(token), expires_at=expires_at)
    url = "/auth/password-reset/confirm"
    data = {"token": token, "new_password": "newpass123"}
    response = api_client.post(url, json=data)
    assert response.status_code == 200
    assert "Password has been reset successfully" in response.json()["detail"]
    # Password should be changed
    user.refresh_from_db()
    assert user.check_password("newpass123")
    # PendingPasswordReset should be deleted
    assert not PendingPasswordReset.objects.filter(token=hash_token(token)).exists()

@pytest.mark.django_db
def test_password_reset_confirm_invalid_token(api_client):
    url = "/auth/password-reset/confirm"
    data = {"token": "invalidtoken", "new_password": "irrelevant"}
    response = api_client.post(url, json=data)
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower() or "expired" in response.json()["detail"].lower()

@pytest.mark.django_db
def test_password_reset_confirm_expired_token(api_client):
    user = create_test_user(email="expired@example.com", password="oldpassword")
    from django.utils import timezone
    import secrets
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() - timezone.timedelta(hours=1)  # Already expired
    from accounts.models import PendingPasswordReset
    PendingPasswordReset.objects.create(user=user, token=hash_token(token), expires_at=expires_at)
    url = "/auth/password-reset/confirm"
    data = {"token": token, "new_password": "newpass123"}
    response = api_client.post(url, json=data)
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()
    # PendingPasswordReset should be deleted
    assert not PendingPasswordReset.objects.filter(token=hash_token(token)).exists()
