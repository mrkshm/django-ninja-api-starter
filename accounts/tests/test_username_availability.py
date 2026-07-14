import pytest
from django.contrib.auth import get_user_model
from urllib.parse import urlencode

User = get_user_model()


@pytest.mark.django_db
def test_check_username_hardcoded(api_client):
    # Hardcoded test: just check that ?username=he returns 200
    url = "/users/check_username"
    params = {"username": "he"}
    print(f"Requesting: {url}?{urlencode(params)}")
    response = api_client.get(f"{url}?{urlencode(params)}")
    print(f"Response: {response.status_code}", response.json())
    assert response.status_code == 200


@pytest.mark.django_db
def test_check_username_available(api_client):
    url = "/users/check_username"
    params = {"username": "unique_username"}
    print(f"Requesting: {url}?{urlencode(params)}")
    response = api_client.get(f"{url}?{urlencode(params)}")
    print(f"Response: {response.status_code}", response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True


@pytest.mark.django_db
def test_check_username_taken(api_client):
    user = User.objects.create_user(
        email="taken@example.com", password="pw", username="takenuser"
    )
    url = "/users/check_username"
    params = {"username": "takenuser"}
    print(f"Requesting: {url}?{urlencode(params)}")
    response = api_client.get(f"{url}?{urlencode(params)}")
    print(f"Response: {response.status_code}", response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert "taken" in data["reason"].lower()
