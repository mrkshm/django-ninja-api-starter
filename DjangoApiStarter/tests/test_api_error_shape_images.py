from django.test import TestCase
from ninja.testing import TestClient
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from organizations.models import Organization, Membership
from ..api import api


class TestApiErrorShapeImages(TestCase):
    def setUp(self):
        User = get_user_model()
        self.member = User.objects.create_user(email="member@example.com", password="pass12345")
        self.org = Organization.objects.create(name="Acme", slug="acme", creator=self.member)
        Membership.objects.create(user=self.member, organization=self.org, role="owner")
        self.client = TestClient(api)

    def _get_auth_headers(self, user):
        # Get a valid JWT token for the user
        resp = self.client.post("/token/pair", json={"email": user.email, "password": "pass12345"})
        access = resp.json()["access"]
        return {"Authorization": f"Bearer {access}"}

    def test_unauthenticated_upload_returns_401_with_detail(self):
        # Do not mock auth and do not set Authorization header
        url = f"/images/orgs/{self.org.slug}/images/"  # Note: relative to API root
        fake = SimpleUploadedFile("test.txt", b"hello", content_type="text/plain")
        resp = self.client.post(url, FILES={"file": fake})
        self.assertEqual(resp.status_code, 401)
        self.assertIsInstance(resp.json(), dict)
        self.assertIn("detail", resp.json())

    def test_invalid_file_type_returns_400_with_detail(self):
        headers = self._get_auth_headers(self.member)
        url = f"/images/orgs/{self.org.slug}/images/"  # Note: relative to API root
        # Not an image MIME -> should hit invalid type branch and return normalized error
        fake = SimpleUploadedFile("test.txt", b"hello", content_type="text/plain")
        resp = self.client.post(url, FILES={"file": fake}, headers=headers)
        self.assertEqual(resp.status_code, 400)
        self.assertIsInstance(resp.json(), dict)
        self.assertIn("detail", resp.json())
