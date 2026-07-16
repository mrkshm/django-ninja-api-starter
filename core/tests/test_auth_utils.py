from types import SimpleNamespace

import pytest
from ninja.errors import HttpError

from core.utils.auth_utils import (
    get_request_user,
    require_authenticated_user,
)


class DummyUser:
    def __init__(self, is_authenticated):
        self.is_authenticated = is_authenticated


def test_require_authenticated_user_none():
    with pytest.raises(HttpError) as exc:
        require_authenticated_user(None)
    assert exc.value.status_code == 401
    assert "Authentication required" in str(exc.value)


def test_require_authenticated_user_false():
    user = DummyUser(is_authenticated=False)
    with pytest.raises(HttpError) as exc:
        require_authenticated_user(user)
    assert exc.value.status_code == 401
    assert "Authentication required" in str(exc.value)


def test_require_authenticated_user_true():
    user = DummyUser(is_authenticated=True)
    require_authenticated_user(user)  # Should not raise


def test_get_request_user_returns_auth_user():
    user = DummyUser(is_authenticated=True)

    assert get_request_user(SimpleNamespace(auth=user, user=object())) is user


def test_get_request_user_does_not_fall_back_to_request_user():
    session_user = DummyUser(is_authenticated=True)

    with pytest.raises(HttpError) as exc:
        get_request_user(SimpleNamespace(auth=None, user=session_user))

    assert exc.value.status_code == 401
