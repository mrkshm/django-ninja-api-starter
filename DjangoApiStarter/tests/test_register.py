from django.test import TestCase
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
        User.objects.create_user(email=email, password=password)
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
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertIsInstance(data["access"], str)
        self.assertIsInstance(data["refresh"], str)
        self.assertEqual(data["access"].count("."), 2, "Access token is not a valid JWT")
        self.assertEqual(data["refresh"].count("."), 2, "Refresh token is not a valid JWT")
