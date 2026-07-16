import pytest
from django.contrib import admin
from django.test import RequestFactory
from ninja.testing import TestClient

from accounts.admin import UserAdmin
from accounts.models import AuthSession, User
from accounts.services import deactivate_user, set_user_active_status
from accounts.tests.utils import create_test_user
from DjangoApiStarter.api import api


def login(client, user, password="testpassword"):
    response = client.post(
        "/token/pair", json={"email": user.email, "password": password}
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.django_db
def test_deactivation_revokes_tokens_permanently_across_reactivation():
    client = TestClient(api)
    user = create_test_user(email="deactivate@example.com")
    tokens = login(client, user)
    session = AuthSession.objects.get(user=user)
    original_auth_version = user.auth_version

    deactivate_user(user)

    session.refresh_from_db()
    assert user.is_active is False
    assert user.auth_version == original_auth_version + 1
    assert session.revoked_at is not None
    assert client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access']}"},
    ).status_code in {401, 403}
    assert (
        client.post("/token/refresh", json={"refresh": tokens["refresh"]}).status_code
        == 401
    )

    set_user_active_status(user, is_active=True)

    assert user.is_active is True
    assert client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access']}"},
    ).status_code in {401, 403}
    assert (
        client.post("/token/refresh", json={"refresh": tokens["refresh"]}).status_code
        == 401
    )


@pytest.mark.django_db
def test_rejected_refresh_commits_session_revocation():
    client = TestClient(api)
    user = create_test_user(email="inactive-refresh@example.com")
    tokens = login(client, user)
    session = AuthSession.objects.get(user=user)
    User.objects.filter(pk=user.pk).update(is_active=False)

    assert client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access']}"},
    ).status_code in {401, 403}
    response = client.post("/token/refresh", json={"refresh": tokens["refresh"]})

    assert response.status_code == 401
    session.refresh_from_db()
    assert session.revoked_at is not None


@pytest.mark.django_db
def test_admin_status_change_revokes_sessions():
    client = TestClient(api)
    user = create_test_user(email="admin-deactivate@example.com")
    login(client, user)
    session = AuthSession.objects.get(user=user)
    original_auth_version = user.auth_version
    user.is_active = False
    user_admin = UserAdmin(User, admin.site)

    user_admin.save_model(
        RequestFactory().post("/admin/"), user, form=None, change=True
    )

    session.refresh_from_db()
    user.refresh_from_db()
    assert user.is_active is False
    assert user.auth_version == original_auth_version + 1
    assert session.revoked_at is not None
