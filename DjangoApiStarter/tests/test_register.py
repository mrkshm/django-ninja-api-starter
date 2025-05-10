from django.test import TestCase
from accounts.tests.utils import create_test_user
from ninja.testing import TestClient
from ..api import api
from ninja.main import NinjaAPI

class TestRegister(TestCase):
    def setUp(self):
        NinjaAPI._registry.clear()
        self.client = TestClient(api)

    def test_register_missing_fields(self):
        # Missing password
        response = self.client.post("/auth/register/", json={"email": "user@example.com"})
        self.assertIn(response.status_code, [400, 422])
        data = response.json()
        self.assertTrue("detail" in data or "message" in data)

        # Missing email
        response = self.client.post("/auth/register/", json={"password": "testpass123"})
        self.assertIn(response.status_code, [400, 422])
        data = response.json()
        self.assertTrue("detail" in data or "message" in data)

        # Missing both
        response = self.client.post("/auth/register/", json={})
        self.assertIn(response.status_code, [400, 422])
        data = response.json()
        self.assertTrue("detail" in data or "message" in data)

    def test_register_existing_email(self):
        from accounts.models import User
        email = "existing@example.com"
        password = "testpass123"
        create_test_user(email=email, password=password)
        response = self.client.post("/auth/register/", json={"email": email, "password": password})
        self.assertIn(response.status_code, [400, 422])
        data = response.json()
        self.assertTrue("detail" in data or "message" in data)

    def test_register_success(self):
        # Register a new user with valid data
        email = "newuser@example.com"
        password = "testpass123"
        response = self.client.post("/auth/register/", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Registration should return a verification message, not tokens
        self.assertIn("detail", data)
        self.assertIn("verify", data["detail"].lower())
