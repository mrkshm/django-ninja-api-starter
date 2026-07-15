import pytest
from ninja.main import NinjaAPI
from ninja.testing import TestClient

from accounts.models import PendingRegistration, User
from accounts.tests.utils import create_test_user
from DjangoApiStarter.api import api


@pytest.mark.django_db
class TestRegister:
    def setup_method(self):
        NinjaAPI._registry.clear()
        self.client = TestClient(api)

    def test_register_requires_email_and_forbids_password(self):
        missing = self.client.post("/auth/register/", json={})
        extra = self.client.post(
            "/auth/register/",
            json={"email": "user@example.com", "password": "not-accepted-here"},
        )

        assert missing.status_code in {400, 422}
        assert extra.status_code in {400, 422}

    def test_register_existing_email_is_generic(self):
        create_test_user(email="existing@example.com", password="testpass123")

        response = self.client.post(
            "/auth/register/", json={"email": "Existing@Example.com"}
        )

        assert response.status_code == 200
        assert "verification email" in response.json()["detail"]
        assert User.objects.filter(email__iexact="existing@example.com").count() == 1
        assert not PendingRegistration.objects.filter(
            email__iexact="existing@example.com"
        ).exists()

    def test_register_success_creates_pending_identity_only(self):
        email = "newuser@example.com"

        response = self.client.post("/auth/register/", json={"email": email})

        assert response.status_code == 200
        assert "verification email" in response.json()["detail"]
        assert PendingRegistration.objects.filter(email=email).exists()
        assert not User.objects.filter(email=email).exists()
