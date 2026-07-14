import pytest
from accounts.tests.utils import create_test_user
from ninja.testing import TestClient
from ..api import api
from ninja.main import NinjaAPI

@pytest.mark.django_db
class TestLogout:
    def setup_method(self):
        NinjaAPI._registry.clear()
        self.client = TestClient(api)

    def test_logout_no_token(self):
        # Call logout with no token
        response = self.client.post("/auth/logout/")
        assert response.status_code == 200
        assert response.json()["detail"] == "Logged out successfully."

    def test_logout_with_token(self):
        # Register and login to get a token
        email = "logoutuser@example.com"
        password = "testpass123"
        create_test_user(email=email, password=password)
        token_response = self.client.post("/token/pair", json={"email": email, "password": password})
        access_token = token_response.json()["access"]
        # Call logout with Authorization header
        response = self.client.post("/auth/logout/", headers={"Authorization": f"Bearer {access_token}"})
        assert response.status_code == 200
        assert response.json()["detail"] == "Logged out successfully."
