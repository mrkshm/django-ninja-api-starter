import pytest
from django.urls import reverse, resolve
from django.test import Client

def test_health_check_url():
    client = Client()
    response = client.get("/kamal/up/")
    assert response.status_code == 200
    assert response.content == b"OK"
    # Optionally check that the view is correctly resolved
    match = resolve("/kamal/up/")
    assert match.func.__name__ == "health_check"
