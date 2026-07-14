import pytest
from ninja.testing import TestClient
from ..api import api

@pytest.mark.django_db
class TestHealthCheck:
    def setup_method(self):
        self.client = TestClient(api)

    def test_health_check(self):
        response = self.client.get("/health/")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.data == {"status": "ok"}
