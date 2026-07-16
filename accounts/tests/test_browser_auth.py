import json
from datetime import timedelta

import pytest
from django.conf import settings
from django.test import Client, override_settings
from django.utils import timezone

from accounts.models import AuthSession, PendingRegistration
from accounts.tests.utils import create_test_user
from accounts.tokens import hash_token

pytestmark = pytest.mark.django_db

API_ROOT = "/api/v1/auth/browser"
FRONTEND_ORIGIN = "http://localhost:3000"


def csrf_ready_client() -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    response = client.get(
        f"{API_ROOT}/csrf",
        HTTP_ORIGIN=FRONTEND_ORIGIN,
    )
    assert response.status_code == 200
    return client, response.json()["csrf_token"]


def browser_login(client: Client, csrf_token: str, *, email: str, password: str):
    return client.post(
        f"{API_ROOT}/login",
        data=json.dumps(
            {"email": email, "password": password, "device_name": "Web browser"}
        ),
        content_type="application/json",
        HTTP_ORIGIN=FRONTEND_ORIGIN,
        HTTP_X_CSRFTOKEN=csrf_token,
    )


def browser_post(client: Client, path: str, csrf_token: str):
    return client.post(
        f"{API_ROOT}/{path}",
        data="{}",
        content_type="application/json",
        HTTP_ORIGIN=FRONTEND_ORIGIN,
        HTTP_X_CSRFTOKEN=csrf_token,
    )


def test_csrf_bootstrap_sets_credentialed_cors_cookie_and_returns_token():
    client, csrf_token = csrf_ready_client()

    assert csrf_token
    assert client.cookies[settings.CSRF_COOKIE_NAME]["httponly"] is True
    response = client.get(f"{API_ROOT}/csrf", HTTP_ORIGIN=FRONTEND_ORIGIN)
    assert response.headers["Access-Control-Allow-Origin"] == FRONTEND_ORIGIN
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["Cache-Control"] == "no-store"


def test_login_requires_valid_csrf_and_never_returns_refresh_token():
    email = "browser-login@example.com"
    password = "testpass123"
    create_test_user(email=email, password=password)
    client = Client(enforce_csrf_checks=True)

    rejected = client.post(
        f"{API_ROOT}/login",
        data=json.dumps({"email": email, "password": password}),
        content_type="application/json",
        HTTP_ORIGIN=FRONTEND_ORIGIN,
    )

    assert rejected.status_code == 403
    assert settings.BROWSER_REFRESH_COOKIE_NAME not in rejected.cookies

    client, csrf_token = csrf_ready_client()
    response = browser_login(
        client,
        csrf_token,
        email=email,
        password=password,
    )

    assert response.status_code == 200
    assert set(response.json()) == {"access", "email"}
    cookie = response.cookies[settings.BROWSER_REFRESH_COOKIE_NAME]
    assert cookie.value
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/api/v1/auth/browser/"
    assert int(cookie["max-age"]) == 30 * 24 * 60 * 60
    assert AuthSession.objects.get().device_name == "Web browser"


@override_settings(BROWSER_REFRESH_COOKIE_SECURE=True)
def test_login_marks_refresh_cookie_secure_outside_local_development():
    email = "browser-secure-cookie@example.com"
    password = "testpass123"
    create_test_user(email=email, password=password)
    client, csrf_token = csrf_ready_client()

    response = browser_login(client, csrf_token, email=email, password=password)

    assert response.status_code == 200
    assert response.cookies[settings.BROWSER_REFRESH_COOKIE_NAME]["secure"] is True


def test_login_rejects_untrusted_origin_even_with_valid_csrf_token():
    email = "browser-origin@example.com"
    password = "testpass123"
    create_test_user(email=email, password=password)
    client, csrf_token = csrf_ready_client()

    response = client.post(
        f"{API_ROOT}/login",
        data=json.dumps({"email": email, "password": password}),
        content_type="application/json",
        HTTP_ORIGIN="https://attacker.example.net",
        HTTP_X_CSRFTOKEN=csrf_token,
    )

    assert response.status_code == 403
    assert not AuthSession.objects.exists()


def test_refresh_rotates_cookie_and_replay_revokes_browser_session():
    email = "browser-refresh@example.com"
    password = "testpass123"
    create_test_user(email=email, password=password)
    client, csrf_token = csrf_ready_client()
    login = browser_login(client, csrf_token, email=email, password=password)
    original_refresh = login.cookies[settings.BROWSER_REFRESH_COOKIE_NAME].value

    refreshed = browser_post(client, "refresh", csrf_token)

    assert refreshed.status_code == 200
    assert set(refreshed.json()) == {"access"}
    rotated_refresh = refreshed.cookies[settings.BROWSER_REFRESH_COOKIE_NAME].value
    assert rotated_refresh != original_refresh

    client.cookies[settings.BROWSER_REFRESH_COOKIE_NAME] = original_refresh
    replay = browser_post(client, "refresh", csrf_token)
    assert replay.status_code == 401
    assert replay.cookies[settings.BROWSER_REFRESH_COOKIE_NAME]["max-age"] == 0

    client.cookies[settings.BROWSER_REFRESH_COOKIE_NAME] = rotated_refresh
    after_replay = browser_post(client, "refresh", csrf_token)
    assert after_replay.status_code == 401
    assert AuthSession.objects.get().revoked_at is not None


def test_logout_is_idempotent_revokes_session_and_clears_cookie():
    email = "browser-logout@example.com"
    password = "testpass123"
    create_test_user(email=email, password=password)
    client, csrf_token = csrf_ready_client()
    browser_login(client, csrf_token, email=email, password=password)

    response = browser_post(client, "logout", csrf_token)

    assert response.status_code == 200
    cleared = response.cookies[settings.BROWSER_REFRESH_COOKIE_NAME]
    assert cleared["max-age"] == 0
    assert cleared["httponly"] is True
    assert cleared["path"] == settings.BROWSER_REFRESH_COOKIE_PATH
    assert AuthSession.objects.get().revoked_at is not None

    repeated = browser_post(client, "logout", csrf_token)
    assert repeated.status_code == 200


def test_browser_registration_sets_cookie_without_exposing_refresh_token():
    raw_token = "browser_registration_token"
    PendingRegistration.objects.create(
        email="browser-register@example.com",
        token=hash_token(raw_token),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    client, csrf_token = csrf_ready_client()

    response = client.post(
        f"{API_ROOT}/verify-registration",
        data=json.dumps(
            {
                "token": raw_token,
                "password": "securepassword123",
                "device_name": "Firefox",
            }
        ),
        content_type="application/json",
        HTTP_ORIGIN=FRONTEND_ORIGIN,
        HTTP_X_CSRFTOKEN=csrf_token,
    )

    assert response.status_code == 200
    assert set(response.json()) == {"detail", "access", "email"}
    assert "refresh" not in response.json()
    assert response.cookies[settings.BROWSER_REFRESH_COOKIE_NAME].value
    assert AuthSession.objects.get().device_name == "Firefox"
