from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import PendingRegistration
from accounts.tokens import hash_token
from organizations.models import Organization

User = get_user_model()


@pytest.mark.django_db
def test_register_creates_only_pending_registration(api_client):
    email = "newuser@example.com"

    response = api_client.post("/auth/register/", json={"email": email})

    assert response.status_code == 200
    assert "verification email" in response.json()["detail"]
    assert not User.objects.filter(email=email).exists()
    assert not Organization.objects.filter(creator__email=email).exists()
    pending = PendingRegistration.objects.get(email=email)
    assert len(pending.token) == 64


@pytest.mark.django_db
def test_register_normalizes_email_at_schema_boundary(api_client):
    with patch("accounts.api.send_verification_email"):
        response = api_client.post(
            "/auth/register/",
            json={"email": "  New.User@EXAMPLE.COM  "},
        )

    assert response.status_code == 200
    assert PendingRegistration.objects.filter(email="new.user@example.com").exists()


@pytest.mark.django_db
def test_register_rejects_malformed_email_before_persistence(api_client):
    response = api_client.post(
        "/auth/register/",
        json={"email": "not-an-email"},
    )

    assert response.status_code == 400
    assert not PendingRegistration.objects.exists()


@pytest.mark.django_db
def test_verify_registration_creates_verified_user_and_personal_org(api_client):
    token = "test_verification_token"
    PendingRegistration.objects.create(
        email="verifyuser@example.com",
        token=hash_token(token),
        expires_at=timezone.now() + timedelta(hours=1),
    )

    response = api_client.post(
        "/auth/verify-registration",
        json={"token": token, "password": "securepassword123", "device_name": "iPhone"},
    )

    assert response.status_code == 200
    assert "access" in response.json()
    assert "refresh" in response.json()
    user = User.objects.get(email="verifyuser@example.com")
    assert user.email_verified is True
    assert user.check_password("securepassword123")
    assert Organization.objects.filter(type="personal", creator=user).exists()
    assert not PendingRegistration.objects.filter(email=user.email).exists()
    assert user.auth_sessions.get().device_name == "iPhone"


@pytest.mark.django_db
def test_verification_rejects_weak_password_without_consuming_token(api_client):
    token = "weak_password_token"
    pending = PendingRegistration.objects.create(
        email="weak@example.com",
        token=hash_token(token),
        expires_at=timezone.now() + timedelta(hours=1),
    )

    response = api_client.post(
        "/auth/verify-registration",
        json={"token": token, "password": "password"},
    )

    assert response.status_code == 400
    assert PendingRegistration.objects.filter(pk=pending.pk).exists()
    assert not User.objects.filter(email=pending.email).exists()


@pytest.mark.django_db
def test_verify_registration_with_expired_token_deletes_pending(api_client):
    token = "expired_token"
    pending = PendingRegistration.objects.create(
        email="expireduser@example.com",
        token=hash_token(token),
        expires_at=timezone.now() - timedelta(hours=1),
    )

    response = api_client.post(
        "/auth/verify-registration",
        json={"token": token, "password": "securepassword123"},
    )

    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()
    assert not PendingRegistration.objects.filter(pk=pending.pk).exists()
    assert not User.objects.filter(email=pending.email).exists()


@pytest.mark.django_db
def test_register_existing_email_is_generic_and_sends_nothing(api_client):
    User.objects.create_user(
        email="existing@example.com", password="securepassword123", email_verified=True
    )

    with patch("accounts.api.send_verification_email") as send:
        response = api_client.post(
            "/auth/register/", json={"email": "Existing@Example.com"}
        )

    assert response.status_code == 200
    assert "verification email" in response.json()["detail"]
    send.assert_not_called()
    assert not PendingRegistration.objects.filter(
        email__iexact="existing@example.com"
    ).exists()


@pytest.mark.django_db
def test_repeated_registration_rotates_one_pending_record(api_client):
    email = "rotate@example.com"
    with patch("accounts.api.send_verification_email"):
        first = api_client.post("/auth/register/", json={"email": email})
        first_token_hash = PendingRegistration.objects.get(email=email).token
        second = api_client.post("/auth/register/", json={"email": email})

    assert first.status_code == 200
    assert second.status_code == 200
    assert PendingRegistration.objects.filter(email=email).count() == 1
    assert PendingRegistration.objects.get(email=email).token != first_token_hash


@pytest.mark.django_db
def test_resend_verification_creates_pending_without_user(api_client):
    email = "resenduser@example.com"

    response = api_client.post("/auth/resend-verification", json={"email": email})

    assert response.status_code == 200
    assert PendingRegistration.objects.filter(email=email).exists()
    assert not User.objects.filter(email=email).exists()


@pytest.mark.django_db
def test_resend_verification_keeps_malformed_email_response_generic(api_client):
    response = api_client.post(
        "/auth/resend-verification",
        json={"email": "not-an-email"},
    )

    assert response.status_code == 200
    assert "verification email" in response.json()["detail"]
    assert not PendingRegistration.objects.exists()


@pytest.mark.django_db
def test_login_with_unverified_user(settings, api_client):
    settings.REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN = True
    email = "unverifieduser@example.com"
    password = "securepassword123"
    User.objects.create_user(email=email, password=password, email_verified=False)

    response = api_client.post(
        "/token/pair", json={"email": email, "password": password}
    )

    assert response.status_code == 403
    assert response.json()["email_verified"] is False


@pytest.mark.django_db
def test_login_with_verified_user(api_client):
    email = "verifieduser@example.com"
    password = "securepassword123"
    User.objects.create_user(email=email, password=password, email_verified=True)

    response = api_client.post(
        "/token/pair", json={"email": email, "password": password}
    )

    assert response.status_code == 200
    assert "access" in response.json()
    assert "refresh" in response.json()
