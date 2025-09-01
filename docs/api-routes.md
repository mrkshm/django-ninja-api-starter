- POST /api/v1/images/orgs/{org_slug}/images/
  - Single image upload (multipart/form-data `file`)
  - 200 → `ImageOut`
  - Validations:
    - Max file size: `UPLOAD_IMAGE_MAX_BYTES` (default 10MB)
    - Allowed MIME prefixes: `UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES` (default `image/`)
  - Rate limiting: per-user throttle (default `60/h`, configurable via settings `IMAGES_RATE_LIMIT_UPLOAD`)
  - 429 Too Many Requests: rate limit exceeded, retry after delay (see settings overrides below)

### Idempotency for bulk endpoints

Send a unique header per client operation to safely retry without executing the bulk action twice:

```
Idempotency-Key: 6d2cf2af-2f1c-4f64-9ee8-2a9d3c2f3a80
```

- Applies to: `bulk_attach`, `bulk_detach`, `bulk-upload`, `bulk-delete`.
- Scope: per-user + HTTP method + request path.
- TTL: 24 hours.
- Behavior: the first successful response for a given key is cached and returned for subsequent retries.
- Recommended: use a new UUID per logical operation; reuse exactly when retrying the same op.
# Django Ninja API Routes

This document describes all REST API endpoints provided by this project. For full schema details, see the OpenAPI (Swagger) docs.

---

## 1. Authentication & User Management

### JWT Authentication (provided by ninja-jwt)

- POST /api/v1/token/pair # Obtain JWT token pair (login)
- POST /api/v1/token/refresh # Refresh access token
- POST /api/v1/token/verify # Verify access/refresh token

### Custom Auth Endpoints

- POST /api/v1/auth/register # Register a new user (sends verification email)
- GET /api/v1/auth/verify-registration # Verify registration email and activate account (returns JWT tokens)
- POST /api/v1/auth/resend-verification # Resend verification email for unverified accounts
- POST /api/v1/auth/logout # Stateless logout (client deletes tokens)
- DELETE /api/v1/auth/delete # Delete authenticated user's account
- POST /api/v1/auth/change-password # Change password (requires old_password)
- PATCH /api/v1/auth/email # Request email change (sends verification)
- GET /api/v1/auth/email/verify # Verify email change via token
- POST /api/v1/auth/password-reset/request # Request password reset (sends email)
- POST /api/v1/auth/password-reset/confirm # Confirm password reset via token

### User Profile

- GET /api/v1/users/me # Get current authenticated user's profile
- PATCH /api/v1/users/me # Update current authenticated user's profile
- POST /api/v1/users/avatar # Upload user avatar
- DELETE /api/v1/users/avatar # Delete user avatar
- GET /api/v1/users/check_username # Check username availability (query param: username)

---

## 2. Contacts

- GET /api/v1/contacts/ # List all contacts (paginated, for user's orgs)
- POST /api/v1/contacts/ # Create a contact (organization slug in payload)
- GET /api/v1/contacts/{slug}/ # Retrieve a single contact by slug
- PUT /api/v1/contacts/{slug}/ # Update a contact by slug (full update)
- PATCH /api/v1/contacts/{slug}/ # Partial update of a contact
- DELETE /api/v1/contacts/{slug}/ # Delete a contact by slug
- POST /api/v1/contacts/{slug}/avatar/ # Upload avatar for contact
- DELETE /api/v1/contacts/{slug}/avatar/ # Delete avatar for contact

---

## 3. Tags (Polymorphic Tagging)

- GET /api/v1/orgs/{org_slug}/tags/ # List tags for an organization
  - Pagination examples:
    - `GET /api/v1/orgs/{org_slug}/tags/?limit=20&offset=0`
    - `GET /api/v1/orgs/{org_slug}/tags/?limit=50&offset=100`
  - Ordering: `?ordering=name|-name|id|-id` (default: `name`)
- POST /api/v1/orgs/{org_slug}/tags/ # Create a tag for an organization
- PATCH /api/v1/orgs/{org_slug}/tags/{tag_id}/ # Update a tag
- DELETE /api/v1/orgs/{org_slug}/tags/{tag_id}/ # Delete a tag
- POST /api/v1/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/ # Assign tags to an object
  - Body: JSON array of tag names, e.g. `["vip", "newsletter"]` (created if missing in org)
  - 200 → `TagOut[]` where `organization` is the org ID
- DELETE /api/v1/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/{slug}/ # Unassign a single tag by slug from an object
  - 200 → `{ detail: "removed" }`

- GET /api/v1/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/
  - List tags for object (paginated)
  - 200 → List[TagOut]
  - Pagination: `?limit=<n>&offset=<n>`
  - Ordering: `?ordering=name|-name|id|-id` (default: `name`)

**Conventions:**

- All tag endpoints use `org_slug` (never integer ID).
- Polymorphic assignment uses `app_label`, `model`, and `obj_id`.
- Bulk unassign is available at `DELETE /orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/` with body `tag_ids: number[]`.

---

## 4. Images & Polymorphic Attachments

- Configuration
  - `UPLOAD_IMAGE_MAX_BYTES` (default: 10485760)
  - `UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES` (default: `image/`)
  - `NINJA_RATELIMIT_ENABLE` (default: `true`) — global switch for Ninja throttling

- POST /api/v1/images/orgs/{org_slug}/bulk-upload/
  - Upload multiple images at once (multipart/form-data `files[]`)
  - 200 → `BulkUploadResponse[]`
  - Validations:
    - Max file size: `UPLOAD_IMAGE_MAX_BYTES` (default 10MB)
    - Allowed MIME prefixes: `UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES` (default `image/`)
  - Rate limiting: per-user throttle (default `30/h`, configurable via settings `IMAGES_RATE_LIMIT_BULK_UPLOAD`)
  - Supports Idempotency-Key (24h TTL, per-user scope)
  - ImageOut: `{ id, file, url, variants: { original, thumb, sm, md, lg }, title, description, alt_text, organization_id, creator_id, created_at, updated_at }`

- GET /api/v1/images/orgs/{org_slug}/images/
  - List all images for org (paginated)
  - 200 → List[ImageOut]
  - Pagination: `?limit=<n>&offset=<n>` (default page size per LimitOffsetPagination)
  - Ordering: `?ordering=created_at|-created_at|title|-title` (default: `-created_at`)

- GET /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/
  - List images attached to an object (paginated)
  - 200 → List[PolymorphicImageRelationOut]
  - Pagination: `?limit=<n>&offset=<n>`
  - Ordering: defaults to relation `order` then `pk` for stable ordering
  - PolymorphicImageRelationOut: `{ id, image: ImageOut, content_type, object_id, is_cover, order }`

- POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/
  - Attach images to an object
  - Body: `ImageIdsIn { image_ids: number[] }`
  - Behavior:
    - If the object has no primary yet, the first attached becomes primary (`is_cover=true`).
    - Newly attached relations receive `order = max(existing.order) + 1`.
  - 200 → List[PolymorphicImageRelationOut]

- POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_attach/
  - Attach many images to an object in one call
  - Behavior: same defaulting rules as attach (first-ever becomes primary, new items appended by `order`)
  - Rate limiting: per-user throttle (default `60/h`, configurable via settings `IMAGES_RATE_LIMIT_BULK_ATTACH`)
  - 200 → `{ attached: number[] }`
  - Supports Idempotency-Key (see below)

- POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_detach/
  - Detach many images from an object in one call
  - Rate limiting: per-user throttle (default `60/h`, configurable via settings `IMAGES_RATE_LIMIT_BULK_DETACH`)
  - 200 → `{ detached: number[] }`
  - Supports Idempotency-Key (see below)

- DELETE /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/{image_id}/
  - Detach an image from an object
  - 204 No Content

- POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/reorder
  - Reorder images for an object atomically and set primary
  - Body: `{ "image_ids": number[] }` — must include all currently attached image IDs, in the desired order. The first becomes primary (`is_cover=true`).
  - Validations:
    - Request list must include all and only images attached to the object (no omissions/duplicates).
    - All images must belong to the same organization.
    - Membership and object-ownership enforced; returns normalized errors `{ detail: string }`.
  - 200 → List[PolymorphicImageRelationOut] after reordering

- POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/set_cover
  - Set a specific attached image as the cover (primary) without changing order
  - Body: `{ "image_id": number }`
  - Behavior:
    - Transactional and idempotent
    - Validates the image is attached to the target object and belongs to the same organization
    - Clears any existing cover and sets the provided `image_id` as `is_cover=true`
  - 200 → `{ detail: "ok" }`

- POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/unset_cover
  - Unset any current cover (primary) without changing order
  - Body: none
  - Behavior:
    - Transactional and idempotent
    - Sets `is_cover=false` for all relations of the target object
  - 200 → `{ detail: "ok" }`
- POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_attach/
  - Bulk attach images to an object
  - Body: `BulkImageIdsIn { image_ids: number[] }`
  - 200 → `BulkAttachOut { attached: number[] }`
  - Rate limiting: per-user throttle (default `60/h`, configurable via settings `IMAGES_RATE_LIMIT_BULK_ATTACH`)
  - 429 Too Many Requests: rate limit exceeded, retry after delay (see settings overrides below)

- POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_detach/
  - Bulk detach images from an object
  - Body: `BulkImageIdsIn { image_ids: number[] }`
  - 200 → `BulkDetachOut { detached: number[] }`
  - Rate limiting: per-user throttle (default `60/h`, configurable via settings `IMAGES_RATE_LIMIT_BULK_DETACH`)
  - 429 Too Many Requests: rate limit exceeded, retry after delay (see settings overrides below)

- POST /api/v1/images/orgs/{org_slug}/bulk-upload/
  - Upload multiple images at once (multipart/form-data `files[]`)
  - 200 → `BulkUploadResponse[]`
  - Validations:
    - Max file size: `UPLOAD_IMAGE_MAX_BYTES` (default 10MB)
    - Allowed MIME prefixes: `UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES` (default `image/`)
  - Rate limiting: per-user throttle (default `30/h`, configurable via settings `IMAGES_RATE_LIMIT_BULK_UPLOAD`)
  - 429 Too Many Requests: rate limit exceeded, retry after delay (see settings overrides below)

- POST /api/v1/images/orgs/{org_slug}/bulk-delete/
  - Bulk delete images
  - Body: `BulkImageIdsIn { image_ids: number[] }`
  - 200 → `BulkDeleteOut { deleted: number[] }`
  - Rate limiting: per-user throttle (default `30/h`, configurable via settings `IMAGES_RATE_LIMIT_BULK_DELETE`)
  - 429 Too Many Requests: rate limit exceeded, retry after delay (see settings overrides below)
Notes:
- Variant URLs are provided for all image responses via `variants` with sizes: `original`, `thumb`, `sm`, `md`, `lg`.
- Mutation endpoints return either 200 with a response body or 204 with no body (for detach).
- All image endpoints use `org_slug`; polymorphic targeting uses `app_label`, `model`, `obj_id`.

### Relation ordering & primary

- Ordering and primary live on the relation (`PolymorphicImageRelation`) so the same image can have different positions/primary status per object.
- Database guarantees at most one primary per object via a partial unique constraint.
- Primary can be set in two ways:
  - By reorder: the first in the provided list becomes primary.
  - Directly via `set_cover` / removed via `unset_cover` without changing order.
- Index on `(content_type, object_id, order)` for efficient ordered reads.

---

## 5. Organization Data Export

- POST /api/v1/orgs/{org_slug}/export/ # Export all org data (admin only, async, GDPR-compliant)

---

## 6. Health Check

- GET /api/v1/health # Health check endpoint

---

## Security & Behavior Notes

### Email Verification Flow
- New user registrations require email verification before login is allowed.
- Verification tokens expire after 12 hours.
- Verification emails are sent asynchronously via Celery.
- Users can request a new verification email if the original expires.
- Login attempts for unverified accounts return a clear message prompting verification.

### Password Reset Flow
- Password reset endpoints always return a generic success message, regardless of whether the email exists, to prevent account enumeration.
- Reset tokens are single-use and expire after a short period (default: 2 hours).
- All reset emails are sent asynchronously via Celery.
- No information is leaked about whether an email exists in the system.

### Organization Data Export
- Only organization admins can trigger and access exports.
- Exports are performed asynchronously and delivered as signed download links (valid for 7 days).
- All images and related org data are included in the export ZIP archive.

### General
- All endpoints reference organizations, users, and contacts by their unique slug (never by integer ID).
- Numeric IDs must never be exposed in API responses or accepted in requests (except for internal tag/image IDs).
- The username availability check endpoint is at `/api/v1/users/check_username` and expects the username as a query parameter (e.g., `?username=foo`).
- For Django Ninja TestClient GET requests, always include query parameters directly in the URL string (e.g., `/users/check_username?username=foo`).
- For the most current and detailed API documentation, refer to the rswag-generated OpenAPI docs.

#### Rate limit configuration

Defaults can be overridden in `settings.py`:

```
IMAGES_RATE_LIMIT_UPLOAD = "60/h"
IMAGES_RATE_LIMIT_BULK_UPLOAD = "30/h"
IMAGES_RATE_LIMIT_BULK_DELETE = "30/h"
IMAGES_RATE_LIMIT_BULK_ATTACH = "60/h"
IMAGES_RATE_LIMIT_BULK_DETACH = "60/h"
```

Throttling can be globally toggled (useful for local dev/tests):

```
NINJA_RATELIMIT_ENABLE = True
```

### Error responses

All errors are normalized to the following JSON shape via a global `HttpError` handler:

```json
{ "detail": "<human-readable message>" }
```

Common statuses used across APIs:
- 400 Bad Request — validation failures, bad payloads, invalid file types/sizes
- 403 Forbidden — organization membership or object-ownership violations
- 404 Not Found — missing organization or target resources
- 429 Too Many Requests — per-user rate limit exceeded on throttled endpoints (see settings overrides below)

Notes:
- Validation errors (including schema validation) return 400 with the same `{ "detail": "..." }` shape.
- Some mutation endpoints return `204 No Content` on success when no response body is needed (e.g., image detach).

### Audit logging

The backend emits minimal audit logs for sensitive tag/image mutations using a dedicated logger named `audit`. Logs are structured JSON written to stdout and can be shipped to your log aggregation platform.

Configured in `DjangoApiStarter/settings.py` under `LOGGING` with a custom JSON formatter `core.utils.logging.JSONFormatter`.

Examples of events:
- `audit:image_attach`, `audit:image_bulk_attach`, `audit:image_bulk_detach`, `audit:image_detach`, `audit:image_delete`
- `audit:image_set_cover`, `audit:image_unset_cover`, `audit:image_reorder`
- `audit:tag_create`, `audit:tag_assign`, `audit:tag_bulk_unassign`, `audit:tag_unassign`, `audit:tag_delete`
- `audit:rate_limited` — emitted when a request is throttled (429), includes `user`, `org`, `path`, `rate`, `ip`

Each log line includes at least:
```json
{ "ts": "2025-08-28T08:06:39.123Z", "level": "INFO", "logger": "audit", "msg": "audit:image_attach", "src": "images/api.py:210" }
```

Downstream processors can key off `msg` for event type and optionally parse identifiers present within the message or extend logging calls to pass `extra={"org": ..., "user": ..., "app": ..., "model": ..., "obj": ..., "image": ..., "tag_id": ...}` which the formatter will include as top-level JSON fields.

# End of route documentation
