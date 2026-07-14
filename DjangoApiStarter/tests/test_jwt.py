import pytest
from accounts.tests.utils import create_test_user
from ninja.testing import TestClient
from ..api import api
from ninja.main import NinjaAPI


@pytest.mark.django_db
class TestJWT:
    def setup_method(self):
        NinjaAPI._registry.clear()
        self.client = TestClient(api)

    def test_token_pair_endpoint_exists(self):
        response = self.client.get("/token/pair")
        assert response.status_code == 405
        response = self.client.post("/token/pair", data={})
        assert response.status_code == 400

    def test_token_pair_success(self):
        from accounts.models import User

        email = "testuser@example.com"
        password = "testpass123"
        create_test_user(email=email, password=password)
        response = self.client.post(
            "/token/pair", json={"email": email, "password": password}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access" in data
        assert "refresh" in data
        assert data["email"] == email

    def test_token_pair_invalid_credentials(self):
        from accounts.models import User

        email = "testuser2@example.com"
        password = "testpass123"
        create_test_user(email=email, password=password)
        response = self.client.post(
            "/token/pair", json={"email": email, "password": "wrongpass"}
        )
        assert response.status_code == 401
        data = response.json()
        assert "access" not in data
        assert "refresh" not in data
        response = self.client.post(
            "/token/pair",
            json={"email": "nouser@example.com", "password": "irrelevant"},
        )
        assert response.status_code == 401
        data = response.json()
        assert "access" not in data
        assert "refresh" not in data

    def test_token_pair_missing_fields(self):
        response = self.client.post(
            "/token/pair", json={"email": "someone@example.com"}
        )
        assert response.status_code == 400
        response = self.client.post("/token/pair", json={"password": "irrelevant"})
        assert response.status_code == 400
        response = self.client.post("/token/pair", json={})
        assert response.status_code == 400

    def test_token_pair_jwt_structure(self):
        from accounts.models import User

        email = "jwtstructure@example.com"
        password = "testpass123"
        create_test_user(email=email, password=password)
        response = self.client.post(
            "/token/pair", json={"email": email, "password": password}
        )
        assert response.status_code == 200
        data = response.json()
        for token_name in ("access", "refresh"):
            token = data.get(token_name)
            assert isinstance(token, str)
            assert (
                token.count(".") == 2
            ), f"{token_name} token is not a valid JWT: {token}"

    def test_refresh_token_flow(self):
        from accounts.models import User

        email = "refreshuser@example.com"
        password = "testpass123"
        create_test_user(email=email, password=password)
        response = self.client.post(
            "/token/pair", json={"email": email, "password": password}
        )
        assert response.status_code == 200
        tokens = response.json()
        refresh_token = tokens.get("refresh")
        assert refresh_token is not None
        response = self.client.post("/token/refresh", json={"refresh": refresh_token})
        assert response.status_code == 200
        data = response.json()
        assert "access" in data
        assert "refresh" in data
        assert data["refresh"] != refresh_token
        assert isinstance(data["access"], str)
        assert (
            data["access"].count(".") == 2
        ), "Refreshed access token is not a valid JWT"

        replay = self.client.post("/token/refresh", json={"refresh": refresh_token})
        assert replay.status_code == 401

        # Replay detection revokes the complete device session, including the
        # token returned by the successful rotation.
        after_replay = self.client.post(
            "/token/refresh",
            json={"refresh": data["refresh"]},
        )
        assert after_replay.status_code == 401

    def test_refresh_token_invalid_and_missing(self):
        response = self.client.post(
            "/token/refresh", json={"refresh": "invalid.token.value"}
        )
        assert response.status_code in [401, 400, 422]
        data = response.json()
        assert "detail" in data or "message" in data
        response = self.client.post("/token/refresh", json={})
        assert response.status_code in [400, 422]
        data = response.json()
        assert "detail" in data or "message" in data

    def test_verify_token(self):
        from accounts.models import User

        email = "verifyuser@example.com"
        password = "testpass123"
        create_test_user(email=email, password=password)
        response = self.client.post(
            "/token/pair", json={"email": email, "password": password}
        )
        assert response.status_code == 200
        tokens = response.json()
        access_token = tokens.get("access")
        assert access_token is not None
        response = self.client.post("/token/verify", json={"token": access_token})
        assert response.status_code == 200
        response = self.client.post(
            "/token/verify", json={"token": "invalid.token.value"}
        )
        assert response.status_code in [401, 422, 400]
        data = response.json()
        assert "detail" in data or "message" in data
