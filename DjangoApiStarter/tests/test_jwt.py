from django.test import TestCase
from ninja.testing import TestClient
from ..api import api
from ninja.main import NinjaAPI

class TestJWT(TestCase):
    def setUp(self):
        NinjaAPI._registry.clear()
        self.client = TestClient(api)

    def test_token_pair_endpoint_exists(self):
        response = self.client.get("/token/pair")
        self.assertEqual(response.status_code, 405)
        response = self.client.post("/token/pair", data={})
        self.assertEqual(response.status_code, 400)

    def test_token_pair_success(self):
        from accounts.models import User
        email = "testuser@example.com"
        password = "testpass123"
        User.objects.create_user(email=email, password=password)
        response = self.client.post("/token/pair", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)

    def test_token_pair_invalid_credentials(self):
        from accounts.models import User
        email = "testuser2@example.com"
        password = "testpass123"
        User.objects.create_user(email=email, password=password)
        response = self.client.post("/token/pair", json={"email": email, "password": "wrongpass"})
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertNotIn("access", data)
        self.assertNotIn("refresh", data)
        response = self.client.post("/token/pair", json={"email": "nouser@example.com", "password": "irrelevant"})
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertNotIn("access", data)
        self.assertNotIn("refresh", data)

    def test_token_pair_missing_fields(self):
        response = self.client.post("/token/pair", json={"email": "someone@example.com"})
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/token/pair", json={"password": "irrelevant"})
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/token/pair", json={})
        self.assertEqual(response.status_code, 400)

    def test_token_pair_jwt_structure(self):
        from accounts.models import User
        email = "jwtstructure@example.com"
        password = "testpass123"
        User.objects.create_user(email=email, password=password)
        response = self.client.post("/token/pair", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for token_name in ("access", "refresh"):
            token = data.get(token_name)
            self.assertIsInstance(token, str)
            self.assertEqual(token.count("."), 2, f"{token_name} token is not a valid JWT: {token}")

    def test_refresh_token_flow(self):
        from accounts.models import User
        email = "refreshuser@example.com"
        password = "testpass123"
        User.objects.create_user(email=email, password=password)
        response = self.client.post("/token/pair", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200)
        tokens = response.json()
        refresh_token = tokens.get("refresh")
        self.assertIsNotNone(refresh_token)
        response = self.client.post("/token/refresh", json={"refresh": refresh_token})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access", data)
        self.assertIsInstance(data["access"], str)
        self.assertEqual(data["access"].count("."), 2, "Refreshed access token is not a valid JWT")

    def test_refresh_token_invalid_and_missing(self):
        response = self.client.post("/token/refresh", json={"refresh": "invalid.token.value"})
        self.assertIn(response.status_code, [401, 400, 422])
        data = response.json()
        self.assertTrue("detail" in data or "message" in data)
        response = self.client.post("/token/refresh", json={})
        self.assertIn(response.status_code, [400, 422])
        data = response.json()
        self.assertTrue("detail" in data or "message" in data)

    def test_verify_token(self):
        from accounts.models import User
        email = "verifyuser@example.com"
        password = "testpass123"
        User.objects.create_user(email=email, password=password)
        response = self.client.post("/token/pair", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200)
        tokens = response.json()
        access_token = tokens.get("access")
        self.assertIsNotNone(access_token)
        response = self.client.post("/token/verify", json={"token": access_token})
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/token/verify", json={"token": "invalid.token.value"})
        self.assertIn(response.status_code, [401, 422, 400])
        data = response.json()
        self.assertTrue("detail" in data or "message" in data)
