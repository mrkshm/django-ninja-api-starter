# Remaining API Cleanup

## Context

The starter now carries the same starter-applicable API cleanup as `ll_back`. This document tracks what was cleaned up and what remains intentionally deferred.

## 1. Accounts Auth API Cleanup

Resolved state:

- Auth request/response schemas live in `accounts/schemas.py`.
- `CustomTokenOutputSchema.email` is an explicit required response field.
- Credential checking and token issuing live in `accounts/services.py`.
- `CustomJWTController` still subclasses `NinjaJWTDefaultController`, but the controller body now only coordinates the API response.

Remaining consideration:

- Keep the custom controller only if `ninja-jwt` does not provide a cleaner extension point.
- Existing route tests cover invalid credentials, unverified login, and token response shape.

## 2. Image API Size And Boundaries

Current state:

- `images/api.py` is still large.
- Image response serialization lives in `images/serializers.py`, but the route module still owns listing, relation mutation, ordering, cover selection, metadata updates, upload, delete, bulk behavior, and throttles.

Future option:

- Split `images/api.py` only if a specific behavior area becomes hard to change safely.
- Preserve compatibility for direct imports from `images.api` while migrating tests and callers.

## 3. Image Variant URL Storage Checks

Resolved state:

- `images/serializers.py` builds deterministic stable `/media/<key>` URLs.
- It no longer calls `default_storage.exists()` while serializing image responses.
- Missing variants now return 404 at the media endpoint instead of falling back to the original URL.

## 4. Media Proxy Access Model

Resolved state:

- `images.views.media_serve()` serves `/media/<key>` without object-level auth checks.
- This is documented as an intentional public bearer-style URL policy.

Future option:

- Replace public media URLs with signed URLs or an authenticated media proxy if generated projects need private organization media.

## 5. Image Throttle Compatibility Wrapper

Resolved state:

- The pinned Django Ninja version uses `UserRateThrottle.allow_request(self, request)`.
- `LoggingUserRateThrottle.allow_request()` now calls that signature directly and no longer catches `TypeError`.
- The global test monkeypatch has been simplified to the same signature.

## Not Applicable From `ll_back`

- Catalogue router import cleanup is not applicable because the starter does not include the catalogue app.
- Catalogue/journal `save_or_400()` centralization is not applicable because the starter does not include those route modules.
