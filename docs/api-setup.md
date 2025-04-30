# Django Ninja API Setup: Best Practices for Routers and Testing

## Router Factory Pattern for Robust API and Test Isolation

When building APIs with Django Ninja, it is important to avoid reusing the same `Router` instance across multiple `NinjaAPI` instances (such as your main app and test clients). Doing so can cause errors like:

```
ninja.errors.ConfigError: Router@'/' has already been attached to API
```

### **Best Practice: Use a Router Factory Function**

Define your routers inside a function that returns a new `Router` instance each time it is called. This ensures that each API instance (production or test) gets its own independent set of routes.

**Example:**

```python
# tags/api.py
from ninja import Router

def get_tags_router():
    router = Router(tags=["tags"])
    # ... define all routes here ...
    return router
```

**In your main API setup:**

```python
# DjangoApiStarter/api.py
from tags.api import get_tags_router
api.add_router("/", get_tags_router(), tags=["tags"])
```

**In your test fixtures:**

```python
# conftest.py
from tags.api import get_tags_router

@pytest.fixture(scope="module")
def api_client():
    test_api = NinjaAPI(urls_namespace="test_tags")
    # ... other setup ...
    test_api.add_router("/", get_tags_router())
    return TestClient(test_api)
```

---

## Disabling Rate Limiting (Throttling) in Tests

**Why:**
- Rate limiting can cause flaky or failing tests (e.g., HTTP 429 errors) when running the full suite, especially if multiple tests hit the same endpoints in quick succession.
- Globally disabling rate limiting in your test environment ensures tests are deterministic and fast, unless you are explicitly testing throttling behavior.

**How:**
- Patch the rate limiter to always allow requests in tests, handling both possible method signatures (`allow_request(self, request)` and `allow_request(self, request, view)`).

**Example for Django Ninja:**

```python
# conftest.py
import pytest
import inspect

@pytest.fixture(autouse=True)
def patch_ninja_user_rate_throttle(monkeypatch):
    try:
        from ninja.throttling import UserRateThrottle
    except ImportError:
        return
    sig = inspect.signature(UserRateThrottle.allow_request)
    if len(sig.parameters) == 3:
        monkeypatch.setattr(UserRateThrottle, "allow_request", lambda self, request, view: True)
    else:
        monkeypatch.setattr(UserRateThrottle, "allow_request", lambda self, request: True)
```

---

## Fixture Scope and Monkeypatching
- When using pytest's `monkeypatch` fixture, always use the default (function) scope for your patching fixture, not session or module scope.
- **Why:** Monkeypatch is function-scoped and pytest will error if you try to use it in a broader scope (e.g., `ScopeMismatch`).

---

## How to Explicitly Test Throttling
- If you want to test the throttling behavior itself, you can temporarily restore the original `allow_request` method or set the relevant setting to `True` in a specific test.

**Example:**
```python
def test_throttling_behavior(monkeypatch):
    from ninja.throttling import UserRateThrottle
    # Optionally restore or patch as needed for this test
    # ... test logic ...
```

---

## Troubleshooting
- If you see errors like `ScopeMismatch` or `TypeError: ... missing 1 required positional argument: 'view'`, it's likely due to fixture scope or method signature mismatches in monkeypatching.
- Always check the method signature and patch accordingly.

---

## Password Reset API Endpoints

The API provides endpoints for requesting a password reset and confirming the reset using a secure token. This flow is stateful and uses Celery for background email delivery.

## Request Password Reset

- **Endpoint:** `POST /api/v1/auth/password-reset/request`
- **Body:** `{ "email": "user@example.com" }`
- **Response:** Always returns a generic success message (even if email does not exist)
- **Behavior:**
  - Generates a secure, time-limited token if the user exists
  - Sends a password reset email asynchronously via Celery
  - No information is leaked about account existence

## Confirm Password Reset

- **Endpoint:** `POST /api/v1/auth/password-reset/confirm`
- **Body:** `{ "token": "...", "new_password": "..." }`
- **Response:** `{ "detail": "Password has been reset successfully." }` on success, or a generic error if the token is invalid or expired

**Security:**
- Tokens are single-use and expire after a short period (default: 2 hours)
- No information is leaked about whether an email exists in the system
- All email sending is handled asynchronously via Celery

**See also:** [core/email_templates/password_reset.txt](../core/email_templates/password_reset.txt)

---

## Organization Data Export (GDPR-Compliant)

Admins can export all organization data (users, contacts, tags, images, etc.) in a single ZIP archive for compliance or backup. The export is performed asynchronously via Celery, includes all images, and is delivered as a signed S3 download link via email.

- **Trigger export:** `POST /api/v1/orgs/{org_slug}/export/` (admin only)
- **Includes:** All org users, contacts (with tags), tags, and images (as files in a subfolder)
- **Delivery:** Download link sent by email, valid for 7 days
- **Security:** Only org admins can trigger and access exports

---

## Why is this best practice?

- **Avoids router re-use errors:** Each API instance gets its own router, preventing Django Ninja's attachment errors.
- **Test isolation:** Tests and production code do not interfere with each other's routes or state.
- **Explicit and scalable:** Easy to extend as your project grows—just use the factory pattern for all routers.
- **Recommended by both Django Ninja and pytest communities.**

---

## References

- [Django Ninja Testing Guide](https://django-ninja.dev/guides/testing/)
- [pytest Fixtures Best Practices](https://docs.pytest.org/en/stable/how-to/fixtures.html)

---

By following these patterns, your API and tests will be robust, maintainable, and free from router attachment and rate limiting issues.
