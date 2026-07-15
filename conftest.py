from types import SimpleNamespace

import pytest
from django.core.cache import cache
from ninja import NinjaAPI
from ninja.testing import TestClient

from DjangoApiStarter.api import api as project_api


def pytest_configure():
    if not hasattr(NinjaAPI, "_registry"):
        NinjaAPI._registry = SimpleNamespace(clear=lambda: None)


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def bypass_throttles(monkeypatch):
    """Explicit opt-out for a test whose request volume is unrelated to throttling."""
    from ninja.throttling import SimpleRateThrottle

    monkeypatch.setattr(SimpleRateThrottle, "allow_request", lambda self, request: True)


@pytest.fixture(scope="function")
def api_client():
    # Use the main project API to prevent re-attaching shared routers
    try:
        NinjaAPI._registry.clear()
    except Exception:
        pass
    return TestClient(project_api)


@pytest.fixture
def make_auth_headers():
    """Return a callable that generates Bearer auth headers for a user via /token/pair."""

    def _make(client: TestClient, user, password: str = "pw") -> dict[str, str]:
        from accounts.services import issue_token_pair

        access, _refresh = issue_token_pair(user)
        return {"Authorization": f"Bearer {access}"}

    return _make
