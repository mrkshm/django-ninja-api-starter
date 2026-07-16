from urllib.parse import urlencode

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def auth_headers(api_client, make_auth_headers):
    user = User.objects.create_user(email="username-checker@example.com", password="pw")
    return make_auth_headers(api_client, user)


@pytest.mark.django_db
def test_check_username_hardcoded(api_client, auth_headers):
    # Hardcoded test: just check that ?username=he returns 200
    url = "/users/check_username"
    params = {"username": "he"}
    print(f"Requesting: {url}?{urlencode(params)}")
    response = api_client.get(f"{url}?{urlencode(params)}", headers=auth_headers)
    print(f"Response: {response.status_code}", response.json())
    assert response.status_code == 200


@pytest.mark.django_db
def test_check_username_available(api_client, auth_headers):
    url = "/users/check_username"
    params = {"username": "unique_username"}
    print(f"Requesting: {url}?{urlencode(params)}")
    response = api_client.get(f"{url}?{urlencode(params)}", headers=auth_headers)
    print(f"Response: {response.status_code}", response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True


@pytest.mark.django_db
def test_check_username_taken(api_client, auth_headers):
    user = User.objects.create_user(
        email="taken@example.com", password="pw", username="takenuser"
    )
    url = "/users/check_username"
    params = {"username": "takenuser"}
    print(f"Requesting: {url}?{urlencode(params)}")
    response = api_client.get(f"{url}?{urlencode(params)}", headers=auth_headers)
    print(f"Response: {response.status_code}", response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert "taken" in data["reason"].lower()


@pytest.mark.django_db
def test_check_username_requires_authentication(api_client):
    response = api_client.get("/users/check_username?username=someone")
    assert response.status_code == 401


@pytest.mark.django_db
def test_check_username_is_throttled(api_client, auth_headers):
    for attempt in range(31):
        response = api_client.get(
            f"/users/check_username?username=candidate{attempt}",
            headers=auth_headers,
        )

    assert response.status_code == 429
