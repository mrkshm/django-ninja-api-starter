import pytest
from ninja import NinjaAPI
from ninja.testing import TestClient
from tags.api import get_tags_router
import importlib
from django.conf import settings
import inspect

# Globally disable Ninja ratelimit for all tests by default
# (Turn on only for specific tests that explicitly test rate limiting)
def pytest_configure():
    settings.NINJA_RATELIMIT_ENABLE = False

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

@pytest.fixture(scope="module")
def api_client():
    test_api = NinjaAPI(urls_namespace="test_tags")
    obtain_pair_router = importlib.import_module("ninja_jwt.routers.obtain").obtain_pair_router
    test_api.add_router("/token", obtain_pair_router)
    test_api.add_router("/", get_tags_router())
    return TestClient(test_api)