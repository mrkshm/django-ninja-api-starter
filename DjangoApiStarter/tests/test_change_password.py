from django.test import TestCase
from accounts.tests.utils import create_test_user
from ninja.testing import TestClient
from ..api import api
from ninja.main import NinjaAPI

class TestChangePassword(TestCase):
    def setUp(self):
        NinjaAPI._registry.clear()
        self.client = TestClient(api)

    def test_change_password_requires_auth(self):
        response = self.client.post("/auth/change-password/", json={"old_password": "x", "new_password": "y"})
        self.assertIn(response.status_code, [401, 403])

    def test_change_password_wrong_old(self):
        email = "changepass@example.com"
        password = "oldpass123"
        create_test_user(email=email, password=password)
        token_response = self.client.post("/token/pair", json={"email": email, "password": password})
        access_token = token_response.json()["access"]
        response = self.client.post(
            "/auth/change-password/",
            json={"old_password": "wrongpass", "new_password": "newpass456"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("incorrect", response.json()["detail"])

    def test_change_password_success(self):
        email = "changepass2@example.com"
        old_password = "oldpass123"
        new_password = "newpass456"
        create_test_user(email=email, password=old_password)
        token_response = self.client.post("/token/pair", json={"email": email, "password": old_password})
        access_token = token_response.json()["access"]
        response = self.client.post(
            "/auth/change-password/",
            json={"old_password": old_password, "new_password": new_password},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("successfully", response.json()["detail"])
        # Login with new password should work
        login_response = self.client.post("/token/pair", json={"email": email, "password": new_password})
        self.assertEqual(login_response.status_code, 200)
        # Login with old password should fail
        login_fail = self.client.post("/token/pair", json={"email": email, "password": old_password})
        self.assertEqual(login_fail.status_code, 401)
