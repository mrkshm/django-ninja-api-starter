import pytest
from ninja.testing import TestClient

from accounts.tests.utils import create_test_user

from ..api import api


@pytest.mark.django_db
class TestChangePassword:
    def setup_method(self):
        self.client = TestClient(api)

    def test_change_password_requires_auth(self):
        response = self.client.post(
            "/auth/change-password/", json={"old_password": "x", "new_password": "y"}
        )
        assert response.status_code in [401, 403]

    def test_change_password_wrong_old(self):
        email = "changepass@example.com"
        password = "oldpass123"
        create_test_user(email=email, password=password)
        token_response = self.client.post(
            "/token/pair", json={"email": email, "password": password}
        )
        access_token = token_response.json()["access"]
        response = self.client.post(
            "/auth/change-password/",
            json={"old_password": "wrongpass", "new_password": "newpass456"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 400
        assert "incorrect" in response.json()["detail"]

    def test_change_password_success(self):
        email = "changepass2@example.com"
        old_password = "oldpass123"
        new_password = "newpass456"
        create_test_user(email=email, password=old_password)
        token_response = self.client.post(
            "/token/pair", json={"email": email, "password": old_password}
        )
        access_token = token_response.json()["access"]
        response = self.client.post(
            "/auth/change-password/",
            json={"old_password": old_password, "new_password": new_password},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        assert "successfully" in response.json()["detail"]
        assert response.json()["reauthentication_required"] is True
        # The password change revokes the session used to perform it.
        old_session = self.client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert old_session.status_code in {401, 403}
        # Login with new password should work
        login_response = self.client.post(
            "/token/pair", json={"email": email, "password": new_password}
        )
        assert login_response.status_code == 200
        # Login with old password should fail
        login_fail = self.client.post(
            "/token/pair", json={"email": email, "password": old_password}
        )
        assert login_fail.status_code == 401
