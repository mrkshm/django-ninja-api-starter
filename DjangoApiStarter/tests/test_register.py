import pytest
from accounts.tests.utils import create_test_user
from ninja.testing import TestClient
from ..api import api
from ninja.main import NinjaAPI

@pytest.mark.django_db
class TestRegister:
    def setup_method(self):
        NinjaAPI._registry.clear()
        self.client = TestClient(api)

    def test_register_missing_fields(self):
        # Missing password
        response = self.client.post("/auth/register/", json={"email": "user@example.com"})
        assert response.status_code in [400, 422]
        data = response.json()
        assert "detail" in data or "message" in data

        # Missing email
        response = self.client.post("/auth/register/", json={"password": "testpass123"})
        assert response.status_code in [400, 422]
        data = response.json()
        assert "detail" in data or "message" in data

        # Missing both
        response = self.client.post("/auth/register/", json={})
        assert response.status_code in [400, 422]
        data = response.json()
        assert "detail" in data or "message" in data

    def test_register_existing_email(self):
        from accounts.models import User
        email = "existing@example.com"
        password = "testpass123"
        create_test_user(email=email, password=password)
        response = self.client.post("/auth/register/", json={"email": email, "password": password})
        assert response.status_code in [400, 422]
        data = response.json()
        assert "detail" in data or "message" in data

    def test_register_success(self):
        # Register a new user with valid data
        email = "newuser@example.com"
        password = "testpass123"
        response = self.client.post("/auth/register/", json={"email": email, "password": password})
        assert response.status_code == 200
        data = response.json()
        # Registration should return a verification message, not tokens
        assert "detail" in data
        assert "verify" in data["detail"].lower()

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            "/auth/register/",
            json={"email": "weak@example.com", "password": "password"},
        )
        assert response.status_code == 400

    def test_register_email_uniqueness_is_case_insensitive(self):
        create_test_user(email="existing@example.com", password="testpass123")
        response = self.client.post(
            "/auth/register/",
            json={"email": "Existing@Example.com", "password": "strong-pass-2947"},
        )
        assert response.status_code == 400
