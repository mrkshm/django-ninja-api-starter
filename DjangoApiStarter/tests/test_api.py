from django.test import TestCase
from ninja.testing import TestClient
from ..api import api

class TestHealthCheck(TestCase):
    def setUp(self):
        self.client = TestClient(api)

    def test_health_check(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.data, {"status": "ok"})
