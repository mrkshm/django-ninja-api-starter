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

- `images/serializers.py` builds deterministic object keys in `variant_keys`.
- It no longer calls `default_storage.exists()` while serializing image responses.
- Missing variants now fail when their signed R2 URL is fetched instead of falling back to the original image.

Why it matters:

- List serialization no longer performs per-image storage network calls on remote storage backends.

## 4. Private Media Access Model

Resolved state:

- Image metadata exposes storage keys through `variant_keys`, not public `/media/<key>` URLs.
- Public/admin-managed images are explicit through `Image.visibility=public` and `public_url`/`public_variant_urls`.
- Private storage uses `R2_PRIVATE_BUCKET_NAME`; public storage helpers use `R2_PUBLIC_BUCKET_NAME`.
- `GET /api/v1/images/orgs/{org_slug}/images/{image_id}/urls` returns short-lived signed R2 URLs after org access checks.
- `ImageShareLink` provides explicit outside-org sharing with revocation and expiry.
- `images.views.media_serve()` is disabled by default and only available when `ALLOW_UNAUTHENTICATED_MEDIA_SERVE=True`.

Why it matters:

- Uploaded images are private organization data, so stable unauthenticated media URLs would be a data exposure risk.

Future option:

- Revisit signed URL TTLs and cache headers once app image caching behavior is measured.

## 5. Image Throttle Compatibility Wrapper

Resolved state:

- The pinned Django Ninja version uses `UserRateThrottle.allow_request(self, request)`.
- `LoggingUserRateThrottle.allow_request()` now calls that signature directly and no longer catches `TypeError`.
- The global test monkeypatch has been simplified to the same signature.

Why it matters:

- Real throttle errors are no longer hidden as signature compatibility failures.

## Priority

Remaining order:

1. Revisit signed URL TTLs and cache headers once app image caching behavior is measured.
2. Move image tests/callers to explicit submodule imports only if the compatibility layer becomes noise.

## Not Applicable From `ll_back`

- Catalogue router import cleanup is not applicable because the starter does not include the catalogue app.
- Catalogue/journal `save_or_400()` centralization is not applicable because the starter does not include those route modules.
