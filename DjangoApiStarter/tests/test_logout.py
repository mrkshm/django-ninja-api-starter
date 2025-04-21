from django.test import TestCase
from ninja.testing import TestClient
from ..api import api
from ninja.main import NinjaAPI

class TestLogout(TestCase):
    def setUp(self):
        NinjaAPI._registry.clear()
        self.client = TestClient(api)

    def test_logout_no_token(self):
        # Call logout with no token
        response = self.client.post("/auth/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "Logged out successfully.")

    def test_logout_with_token(self):
        # Register and login to get a token
        email = "logoutuser@example.com"
        password = "testpass123"
        self.client.post("/auth/register/", json={"email": email, "password": password})
        token_response = self.client.post("/token/pair", json={"email": email, "password": password})
        access_token = token_response.json()["access"]
        # Call logout with Authorization header
        response = self.client.post("/auth/logout/", headers={"Authorization": f"Bearer {access_token}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "Logged out successfully.")
