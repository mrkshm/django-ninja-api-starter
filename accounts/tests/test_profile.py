import pytest
from django.contrib.auth import get_user_model
from accounts.tests.utils import create_test_user
from ninja.testing import TestClient
from DjangoApiStarter.api import api
from ninja.main import NinjaAPI

User = get_user_model()
client = TestClient(api)

@pytest.fixture(autouse=True)
def clear_ninjaapi_registry():
    NinjaAPI._registry.clear()

@pytest.mark.django_db
def test_get_me_success():
    # Create user
    user = create_test_user(email="me@example.com", password="testpass", first_name="Test", last_name="User")
    # Obtain JWT token (using login endpoint)
    response = client.post("/token/pair", json={"email": "me@example.com", "password": "testpass"})
    assert response.status_code == 200
    access = response.json()["access"]

    # Call GET /me with Authorization header
    response = client.get("/users/me", headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@example.com"
    assert data["first_name"] == "Test"
    assert data["last_name"] == "User"

@pytest.mark.django_db
def test_get_me_unauthenticated():
    response = client.get("/users/me")
    assert response.status_code == 401

@pytest.mark.django_db
def test_patch_me_partial_update(settings):
    user = create_test_user(email="patchme@example.com", password="pw", first_name="Old", last_name="Name")
    response = client.post("/token/pair", json={"email": "patchme@example.com", "password": "pw"})
    access = response.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    # Partial update (only first_name)
    response = client.patch("/users/me", json={"first_name": "New"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "New"
    assert data["last_name"] == "Name"

@pytest.mark.django_db
def test_patch_me_invalid_data(settings):
    user = create_test_user(email="invalidpatch@example.com", password="pw", first_name="Valid", last_name="User")
    response = client.post("/token/pair", json={"email": "invalidpatch@example.com", "password": "pw"})
    access = response.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    # Too long first_name (assuming max_length=50)
    long_name = "x" * 100
    response = client.patch("/users/me", json={"first_name": long_name}, headers=headers)
    assert response.status_code == 400 or response.status_code == 422
    # Unsupported field
    response = client.patch("/users/me", json={"not_a_field": "test"}, headers=headers)
    assert response.status_code == 400 or response.status_code == 422

@pytest.mark.django_db
def test_patch_me_unauthenticated():
    response = client.patch("/users/me", json={"first_name": "NoAuth"})
    assert response.status_code == 401

@pytest.mark.django_db
def test_email_change_delivery_failure(monkeypatch, settings):
    from core import tasks as core_tasks
    user = create_test_user(email="failmail@example.com", password="pw")
    response = client.post("/token/pair", json={"email": "failmail@example.com", "password": "pw"})
    access = response.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    def fail_send_email_task(*args, **kwargs):
        raise Exception("Simulated email failure")
    monkeypatch.setattr(core_tasks.send_email_task, "delay", fail_send_email_task)
    response = client.patch("/auth/email", json={"email": "failmail2@example.com"}, headers=headers)
    assert response.status_code == 500 or response.status_code == 400
    assert "fail" in response.json()["detail"].lower() or "error" in response.json()["detail"].lower() or "exception" in response.json()["detail"].lower()

@pytest.mark.django_db
def test_check_username_length_and_uniqueness():
    # Missing username param
    response = client.get("/users/check_username")
    assert response.status_code == 200
    data = response.json()
    print("[TEST LOG] Missing username response:", response.status_code, data)
    assert data["available"] is False
    assert "1-50" in data["reason"]

    # Too long
    long_username = "x" * 51
    response = client.get("/users/check_username", params={"username": long_username})
    assert response.status_code == 200
    data = response.json()
    print("[TEST LOG] Too long username response:", response.status_code, data)
    assert data["available"] is False
    assert "1-50" in data["reason"]

    # Uniqueness (case-insensitive)
    create_test_user(email="taken@example.com", username="TestUser", password="pw")
    username = "testuser"
    response = client.get(f"/users/check_username?username={username}")
    print("[TEST LOG] Uniqueness response:", response.status_code, response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert "taken" in data["reason"].lower()

    # Available
    username = "uniquename"
    response = client.get(f"/users/check_username?username={username}")
    print("[TEST LOG] Available username response:", response.status_code, response.json())
    assert response.status_code == 200
    assert response.json()["available"] is True
