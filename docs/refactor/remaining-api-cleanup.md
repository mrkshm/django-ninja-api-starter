# Remaining API Cleanup

## Context

The starter now carries the same starter-applicable API cleanup as `ll_back`. This document tracks what was cleaned up and what remains intentionally deferred.

## 1. Accounts Auth API Cleanup

Resolved state:

- Auth request/response schemas live in `accounts/schemas.py`.
- `CustomTokenOutputSchema.email` is an explicit required response field.
- Token pair input lives in `accounts/schemas.py`.
- Credential checking and token issuing live in `accounts/services.py`.
- The custom `NinjaJWTDefaultController` subclass has been removed.
- `accounts/api.py` exposes explicit `/token/pair`, `/token/refresh`, and `/token/verify` routes through `token_router`.

Remaining consideration:

- The explicit `/token/pair` endpoint preserves the product-specific verified-email login response.
- Existing route tests cover invalid credentials, unverified login, and token response shape.

## 2. Image API Size And Boundaries

Resolved state:

- The images API is now an `images/api/` package split by behavior.
- Route-local schemas live in `images/api_schemas.py`.
- Throttle setup lives in `images/throttles.py`.
- `images/api/__init__.py` preserves direct imports such as `from images.api import upload_image`.

Why it matters:

- The image API no longer has one large route module mixing listing, relation, upload, metadata, delete, and throttle concerns.

Future option:

- Move tests/callers to explicit submodule imports if the compatibility re-exports become unnecessary.

## 3. Image Variant URL Storage Checks

Resolved state:

- `images/serializers.py` builds deterministic stable `/media/<key>` URLs.
- It no longer calls `default_storage.exists()` while serializing image responses.
- Missing variants now return 404 at the media endpoint instead of falling back to the original URL.

Why it matters:

- List serialization no longer performs per-image storage network calls on remote storage backends.

## 4. Media Proxy Access Model

Resolved state:

- `images.views.media_serve()` serves `/media/<key>` without object-level auth checks.
- This is documented as an intentional public bearer-style URL policy.

Why it matters:

- If generated projects make uploaded images private organization data, stable unauthenticated media URLs would become a data exposure risk.

Future option:

- Replace public media URLs with signed URLs or an authenticated media proxy if generated projects need private organization media.

## 5. Image Throttle Compatibility Wrapper

Resolved state:

- The pinned Django Ninja version uses `UserRateThrottle.allow_request(self, request)`.
- `LoggingUserRateThrottle.allow_request()` now calls that signature directly and no longer catches `TypeError`.
- The global test monkeypatch has been simplified to the same signature.

Why it matters:

- Real throttle errors are no longer hidden as signature compatibility failures.

## Priority

Remaining order:

1. Revisit signed/authenticated media URLs if generated projects need private organization media.
2. Move image tests/callers to explicit submodule imports only if the compatibility layer becomes noise.

## Not Applicable From `ll_back`

- Catalogue router import cleanup is not applicable because the starter does not include the catalogue app.
- Catalogue/journal `save_or_400()` centralization is not applicable because the starter does not include those route modules.
