import pytest
from django.test import Client
from django.urls import resolve


def test_liveness_url_has_no_dependency_checks():
    response = Client().get("/health/live/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert resolve("/health/live/").func.__name__ == "live"


@pytest.mark.django_db
def test_readiness_checks_database_and_cache():
    response = Client().get("/health/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_id_is_returned_and_untrusted_values_are_replaced():
    client = Client()
    supplied = client.get("/health/live/", HTTP_X_REQUEST_ID="ios-request_123")
    rejected = client.get("/health/live/", HTTP_X_REQUEST_ID="bad value with spaces")
    assert supplied.headers["X-Request-ID"] == "ios-request_123"
    assert rejected.headers["X-Request-ID"] != "bad value with spaces"
