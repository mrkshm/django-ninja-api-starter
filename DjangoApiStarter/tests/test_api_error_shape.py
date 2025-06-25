from django.test import TestCase
from ninja.testing import TestClient
from django.contrib.auth import get_user_model
from organizations.models import Organization, Membership
from ..api import api


class TestApiErrorShape(TestCase):
    def setUp(self):
        User = get_user_model()
        self.member = User.objects.create_user(email="member@example.com", password="pass12345")
        self.nonmember = User.objects.create_user(email="nonmember@example.com", password="pass12345")
        self.org = Organization.objects.create(name="Acme", slug="acme", creator=self.member)
        Membership.objects.create(user=self.member, organization=self.org, role="owner")
        self.client = TestClient(api)

    def _get_auth_headers(self, user):
        # Get a valid JWT token for the user
        resp = self.client.post("/token/pair", json={"email": user.email, "password": "pass12345"})
        access = resp.json()["access"]
        return {"Authorization": f"Bearer {access}"}

    def test_invalid_ordering_returns_normalized_400_detail(self):
        headers = self._get_auth_headers(self.member)
        # Note: Ninja TestClient paths are relative to the API root, not the full URL
        resp = self.client.get(f"/orgs/{self.org.slug}/tags/?ordering=bogus", headers=headers)
        self.assertEqual(resp.status_code, 400)
        self.assertIsInstance(resp.json(), dict)
        self.assertIn("detail", resp.json())
        self.assertIn("Invalid ordering", resp.json()["detail"]) 

    def test_nonmember_access_returns_normalized_403_detail(self):
        headers = self._get_auth_headers(self.nonmember)
        # Note: Ninja TestClient paths are relative to the API root, not the full URL
        resp = self.client.get(f"/orgs/{self.org.slug}/tags/", headers=headers)
        self.assertEqual(resp.status_code, 403)
        self.assertIsInstance(resp.json(), dict)
        self.assertIn("detail", resp.json())
        # message can vary; just ensure detail exists
