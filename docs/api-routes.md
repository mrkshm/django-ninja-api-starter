# Django Ninja API Routes

This document describes all REST API endpoints provided by this project. For full schema details, see the OpenAPI (Swagger) docs.

---

## 1. Authentication & User Management

### JWT Authentication (provided by ninja-jwt)

- POST /api/v1/token/pair # Obtain JWT token pair (login)
- POST /api/v1/token/refresh # Refresh access token
- POST /api/v1/token/verify # Verify access/refresh token

### Custom Auth Endpoints

- POST /api/v1/auth/register # Register a new user (returns JWT tokens)
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
- POST /api/v1/orgs/{org_slug}/tags/ # Create a tag for an organization
- PATCH /api/v1/orgs/{org_slug}/tags/{tag_id}/ # Update a tag
- DELETE /api/v1/orgs/{org_slug}/tags/{tag_id}/ # Delete a tag
- POST /api/v1/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/ # Assign tags to an object
- DELETE /api/v1/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/{slug}/ # Unassign a tag from an object

**Conventions:**

- All tag endpoints use `org_slug` (never integer ID).
- Polymorphic assignment uses `app_label`, `model`, and `obj_id`.

---

## 4. Images & Polymorphic Attachments

- POST /api/v1/images/orgs/{org_slug}/images/ # Upload a single image
- GET /api/v1/images/orgs/{org_slug}/images/ # List all images for org
- GET /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/ # List images for object
- PATCH /api/v1/images/orgs/{org_slug}/images/{image_id}/ # Edit image metadata
- DELETE /api/v1/images/orgs/{org_slug}/images/{image_id}/ # Delete image
- POST /api/v1/images/orgs/{org_slug}/bulk-upload/ # Bulk upload images
- POST /api/v1/images/orgs/{org_slug}/bulk-delete/ # Bulk delete images
- POST /api/v1/images/orgs/{org_slug}/attach/ # Attach image polymorphically
- POST /api/v1/images/orgs/{org_slug}/detach/ # Detach image polymorphically
- POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_attach/ # Bulk attach to object
- POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_detach/ # Bulk detach from object
- POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/ # Attach images to object

**Conventions:**

- All image endpoints use `org_slug` (never integer ID).
- Polymorphic attach/detach use `app_label`, `model`, `obj_id`.
- Bulk operations always use POST and accept JSON or multipart/form-data.

---

## 5. Organization Data Export

- POST /api/v1/orgs/{org_slug}/export/ # Export all org data (admin only, async, GDPR-compliant)

---

## 6. Health Check

- GET /api/v1/health # Health check endpoint

---

## Security & Behavior Notes

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

# End of route documentation
