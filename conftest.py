import pytest
import os
from pathlib import Path
from types import SimpleNamespace
from ninja.testing import TestClient
from django.conf import settings
from django.core.cache import cache
from DjangoApiStarter.api import api as project_api
from ninja import NinjaAPI


# Globally disable Ninja ratelimit for all tests by default
# (Turn on only for specific tests that explicitly test rate limiting)
def pytest_configure():
    if not hasattr(NinjaAPI, "_registry"):
        NinjaAPI._registry = SimpleNamespace(clear=lambda: None)
    media_root = Path(settings.BASE_DIR) / ".test_media"
    media_root.mkdir(exist_ok=True)
    settings.MEDIA_ROOT = media_root
    settings.STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {
                "location": str(media_root),
                "base_url": "/media/",
            },
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    try:
        from django.core.files.storage import default_storage, storages
        from django.utils.functional import empty

        storages._storages = {}
        default_storage._wrapped = empty
    except Exception:
        pass
    settings.NINJA_RATELIMIT_ENABLE = False
    settings.DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "django-ninja-api-starter-tests",
        }
    }
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.CELERY_RESULT_BACKEND = "cache+memory://"
    settings.CELERY_BROKER_URL = "memory://"
    # Allow login without verified email for most tests; specific tests can override this
    settings.REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN = False
    # Ensure Ninja registry checks are skipped in tests
    import os as _os

    _os.environ.setdefault("NINJA_SKIP_REGISTRY", "true")
    # Set environment variable to skip Ninja registry validation
    os.environ.setdefault("NINJA_SKIP_REGISTRY", "true")


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def patch_ninja_user_rate_throttle(monkeypatch):
    """
    Patch UserRateThrottle.allow_request to always allow during tests.
    """
    try:
        from ninja.throttling import UserRateThrottle
    except ImportError:
        return  # If not present, skip
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
        from accounts.services import issue_token_pair

        access, _refresh = issue_token_pair(user)
        return {"Authorization": f"Bearer {access}"}

    return _make
