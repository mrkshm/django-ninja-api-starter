from django.test import TestCase
from accounts.tests.utils import create_test_user
from ninja.testing import TestClient
from ..api import api
from ninja.main import NinjaAPI

class TestDeleteAccount(TestCase):
    def setUp(self):
        NinjaAPI._registry.clear()
        self.client = TestClient(api)

    def test_delete_account_requires_auth(self):
        # Should fail without JWT
        response = self.client.delete("/auth/delete/")
        self.assertIn(response.status_code, [401, 403])

    def test_delete_account_success(self):
        # Register and login to get a token
        email = "deleteuser@example.com"
        password = "testpass123"
        create_test_user(email=email, password=password)
        token_response = self.client.post("/token/pair", json={"email": email, "password": password})
        access_token = token_response.json()["access"]
        # Delete account with JWT
        response = self.client.delete("/auth/delete/", headers={"Authorization": f"Bearer {access_token}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "Account deleted successfully.")
        # Further requests with same token should fail
        response = self.client.delete("/auth/delete/", headers={"Authorization": f"Bearer {access_token}"})
        self.assertIn(response.status_code, [401, 403])
