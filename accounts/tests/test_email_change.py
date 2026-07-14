import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from accounts.tests.utils import create_test_user
from accounts.models import PendingEmailChange
from accounts.tokens import hash_token

User = get_user_model()


@pytest.mark.django_db
def test_request_email_change_success(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    user = create_test_user(email="old@example.com", password="pw")
    resp = api_client.post(
        "/token/pair", json={"email": "old@example.com", "password": "pw"}
    )
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    resp = api_client.patch(
        "/auth/email", json={"email": "new@example.com"}, headers=headers
    )
    assert resp.status_code == 200
    assert "Verification email sent" in resp.json()["detail"]
    pending = PendingEmailChange.objects.get(user=user)
    assert pending.new_email == "new@example.com"
    assert len(pending.token) == 64
    assert not pending.is_expired()


@pytest.mark.django_db
def test_verify_email_change_success(settings, api_client):
    user = create_test_user(email="old2@example.com", password="pw")
    token = "testtoken123"
    expires = timezone.now() + timezone.timedelta(hours=1)
    PendingEmailChange.objects.create(
        user=user,
        new_email="new2@example.com",
        token=hash_token(token),
        expires_at=expires,
    )
    resp = api_client.post("/auth/email/verify", json={"token": token})
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.email == "new2@example.com"
    assert not PendingEmailChange.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_verify_email_change_expired_token(settings, api_client):
    user = create_test_user(email="expired@example.com", password="pw")
    token = "expiredtoken123"
    # Set expires_at in the past
    expires = timezone.now() - timezone.timedelta(hours=1)
    PendingEmailChange.objects.create(
        user=user,
        new_email="expired2@example.com",
        token=hash_token(token),
        expires_at=expires,
    )
    resp = api_client.post("/auth/email/verify", json={"token": token})
    assert resp.status_code == 400 or resp.status_code == 410
    assert (
        "expired" in resp.json()["detail"].lower()
        or "invalid" in resp.json()["detail"].lower()
    )


@pytest.mark.django_db
def test_verify_email_change_invalid_token(settings, api_client):
    user = create_test_user(email="invalidtoken@example.com", password="pw")
    # Do NOT create any PendingEmailChange with this token
    token = "doesnotexisttoken"
    resp = api_client.post("/auth/email/verify", json={"token": token})
    assert resp.status_code == 400 or resp.status_code == 404
    assert (
        "invalid" in resp.json()["detail"].lower()
        or "not found" in resp.json()["detail"].lower()
    )


@pytest.mark.django_db
def test_request_email_change_invalid_format(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    user = create_test_user(email="invalid1@example.com", password="pw")
    resp = api_client.post(
        "/token/pair", json={"email": "invalid1@example.com", "password": "pw"}
    )
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    resp = api_client.patch(
        "/auth/email", json={"email": "not-an-email"}, headers=headers
    )
    assert resp.status_code == 400
    assert "Invalid email address" in resp.json()["detail"]


@pytest.mark.django_db
def test_request_email_change_email_taken(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    user1 = create_test_user(email="taken@example.com", password="pw")
    user2 = create_test_user(email="user2@example.com", password="pw")
    resp = api_client.post(
        "/token/pair", json={"email": "user2@example.com", "password": "pw"}
    )
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    resp = api_client.patch(
        "/auth/email", json={"email": "taken@example.com"}, headers=headers
    )
    assert resp.status_code == 400
    assert "Email already taken" in resp.json()["detail"]


@pytest.mark.django_db
def test_multiple_pending_changes(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    user = create_test_user(email="multi@example.com", password="pw")
    resp = api_client.post(
        "/token/pair", json={"email": "multi@example.com", "password": "pw"}
    )
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    # First request
    resp1 = api_client.patch(
        "/auth/email", json={"email": "first@example.com"}, headers=headers
    )
    assert resp1.status_code == 200
    # Second request before verifying
    resp2 = api_client.patch(
        "/auth/email", json={"email": "second@example.com"}, headers=headers
    )
    assert resp2.status_code == 200
    # Only one pending change should exist
    pendings = PendingEmailChange.objects.filter(user=user)
    assert pendings.count() == 1
    assert pendings.first().new_email == "second@example.com"


@pytest.mark.django_db
def test_email_change_after_verification(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    user = create_test_user(email="afterverify@example.com", password="pw")
    token = "verifytoken123"
    expires = timezone.now() + timezone.timedelta(hours=1)
    PendingEmailChange.objects.create(
        user=user,
        new_email="afterverify2@example.com",
        token=hash_token(token),
        expires_at=expires,
    )
    resp = api_client.post("/auth/email/verify", json={"token": token})
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.email == "afterverify2@example.com"
    assert not PendingEmailChange.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_case_insensitive_email_uniqueness(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    create_test_user(email="caseuser@example.com", password="pw")
    user2 = create_test_user(email="other@example.com", password="pw")
    resp = api_client.post(
        "/token/pair", json={"email": "other@example.com", "password": "pw"}
    )
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    # Try to change to same email with different case
    resp = api_client.patch(
        "/auth/email", json={"email": "CaseUser@Example.com"}, headers=headers
    )
    assert resp.status_code == 400
    assert "Email already taken" in resp.json()["detail"]


@pytest.mark.django_db
def test_reusing_token_after_success(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    user = create_test_user(email="reuse@example.com", password="pw")
    token = "reusetoken123"
    expires = timezone.now() + timezone.timedelta(hours=1)
    PendingEmailChange.objects.create(
        user=user,
        new_email="reuse2@example.com",
        token=hash_token(token),
        expires_at=expires,
    )
    # First use (should succeed)
    resp1 = api_client.post("/auth/email/verify", json={"token": token})
    assert resp1.status_code == 200
    user.refresh_from_db()
    assert user.email == "reuse2@example.com"
    # Second use (should fail)
    resp2 = api_client.post("/auth/email/verify", json={"token": token})
    assert resp2.status_code == 400 or resp2.status_code == 404
    assert (
        "invalid" in resp2.json()["detail"].lower()
        or "not found" in resp2.json()["detail"].lower()
    )


@pytest.mark.django_db
def test_verify_email_change_email_taken(api_client):
    from django.utils import timezone
    from accounts.models import PendingEmailChange

    # Create two users
    user1 = create_test_user(email="taken@example.com", password="pw")
    user2 = create_test_user(email="user2@example.com", password="pw")
    # user2 requests to change email to taken@example.com
    token = "tokentaken123"
    expires = timezone.now() + timezone.timedelta(hours=1)
    PendingEmailChange.objects.create(
        user=user2,
        new_email="taken@example.com",
        token=hash_token(token),
        expires_at=expires,
    )
    # Now verify (should fail, delete pending, and return error)
    resp = api_client.post("/auth/email/verify", json={"token": token})
    assert resp.status_code == 400
    assert "Email already taken" in resp.json()["detail"]
    # PendingEmailChange should be deleted
    assert not PendingEmailChange.objects.filter(token=hash_token(token)).exists()


def test_request_email_change_unauthenticated(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    resp = api_client.patch("/auth/email", json={"email": "unauth@example.com"})
    assert resp.status_code == 401
    # Optionally check error message
