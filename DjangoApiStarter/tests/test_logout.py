import pytest
from accounts.tests.utils import create_test_user
from ninja.testing import TestClient
from ..api import api


@pytest.mark.django_db
class TestLogout:
    def setup_method(self):
        self.client = TestClient(api)

    def test_logout_requires_refresh_token(self):
        response = self.client.post("/auth/logout/")
        assert response.status_code == 400

    def test_logout_revokes_session(self):
        email = "logoutuser@example.com"
        password = "testpass123"
        create_test_user(email=email, password=password)
        token_response = self.client.post(
            "/token/pair",
            json={"email": email, "password": password, "device_name": "Test iPhone"},
        )
        tokens = token_response.json()

        response = self.client.post(
            "/auth/logout/",
            json={"refresh": tokens["refresh"]},
        )
        assert response.status_code == 200
        assert response.json()["detail"] == "Logged out successfully."

        refresh_response = self.client.post(
            "/token/refresh",
            json={"refresh": tokens["refresh"]},
        )
        assert refresh_response.status_code == 401

        protected_response = self.client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {tokens['access']}"},
        )
        assert protected_response.status_code in {401, 403}
