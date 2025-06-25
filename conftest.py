import pytest
import os
from ninja.testing import TestClient
from django.conf import settings
import inspect
from DjangoApiStarter.api import api as project_api
from ninja import NinjaAPI

# Globally disable Ninja ratelimit for all tests by default
# (Turn on only for specific tests that explicitly test rate limiting)
def pytest_configure():
    settings.NINJA_RATELIMIT_ENABLE = False
    # Allow login without verified email for most tests; specific tests can override this
    settings.REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN = False
    # Ensure Ninja registry checks are skipped in tests
    import os as _os
    _os.environ.setdefault("NINJA_SKIP_REGISTRY", "true")
    # Set environment variable to skip Ninja registry validation
    os.environ.setdefault("NINJA_SKIP_REGISTRY", "true")

@pytest.fixture(autouse=True)
def patch_ninja_user_rate_throttle(monkeypatch):
    """
    Patch UserRateThrottle.allow_request to always allow during tests,
    regardless of signature (handles both with/without 'view').
    """
    try:
        from ninja.throttling import UserRateThrottle
    except ImportError:
        return  # If not present, skip
    sig = inspect.signature(UserRateThrottle.allow_request)
    if len(sig.parameters) == 3:
        monkeypatch.setattr(UserRateThrottle, "allow_request", lambda self, request, view: True)
    else:
        monkeypatch.setattr(UserRateThrottle, "allow_request", lambda self, request: True)


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
        resp = client.post("/token/pair", json={"email": user.email, "password": password})
        assert resp.status_code == 200, f"Failed to get token for {user.email}: {resp.status_code} {resp.content}"
        access = resp.json()["access"]
        return {"Authorization": f"Bearer {access}"}
    return _make