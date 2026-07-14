import pytest
from accounts.tests.utils import create_test_user
from ninja.testing import TestClient
from ..api import api
from ninja.main import NinjaAPI


@pytest.mark.django_db
class TestDeleteAccount:
    def setup_method(self):
        NinjaAPI._registry.clear()
        self.client = TestClient(api)

    def test_delete_account_requires_auth(self):
        # Should fail without JWT
        response = self.client.delete("/auth/delete/")
        assert response.status_code in [401, 403]

    def test_delete_account_success(self):
        # Register and login to get a token
        email = "deleteuser@example.com"
        password = "testpass123"
        create_test_user(email=email, password=password)
        token_response = self.client.post(
            "/token/pair", json={"email": email, "password": password}
        )
        access_token = token_response.json()["access"]
        # Delete account with JWT and current password
        response = self.client.delete(
            "/auth/delete/",
            json={"password": password},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        assert response.json()["detail"] == "Account deleted successfully."
        # Further requests with same token should fail
        response = self.client.delete(
            "/auth/delete/",
            json={"password": password},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code in [401, 403]

    def test_delete_account_rejects_wrong_password(self):
        email = "deletewrong@example.com"
        password = "testpass123"
        user = create_test_user(email=email, password=password)
        token_response = self.client.post(
            "/token/pair", json={"email": email, "password": password}
        )
        access_token = token_response.json()["access"]

        response = self.client.delete(
            "/auth/delete/",
            json={"password": "wrong-password"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Password is incorrect"
        assert type(user).objects.filter(id=user.id).exists()
