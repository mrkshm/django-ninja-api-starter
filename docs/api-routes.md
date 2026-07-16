# API routes and conventions

The generated [OpenAPI contract](openapi.json) is authoritative. CI regenerates
it and fails on drift. Interactive documentation is mounted at `/api/v1/docs`;
API operations are versioned below `/api/v1`.

## Conventions

- Organization-owned resources use `/orgs/{org_slug}/<resource>/...`.
- A resource belonging to another tenant is treated as not found.
- Collection GET routes use limit/offset pagination where declared in OpenAPI.
- JSON validation errors use `detail` plus sanitized `errors`; application
  errors use `detail`. Unhandled errors include a request ID, never internals.
- Conflicting uniqueness writes return `409`; invalid input returns `400`.
- Breaking contract changes require a new API version and regenerated OpenAPI.
- Credential responses that revoke existing sessions include
  `reauthentication_required: true`; clients must discard both token types.

## Route groups

| Purpose | Routes |
| --- | --- |
| Sessions | `POST /token/pair`, `/token/refresh`, `/token/verify` |
| Browser sessions | `GET /auth/browser/csrf`; `POST /auth/browser/login`, `/auth/browser/verify-registration`, `/auth/browser/refresh`, `/auth/browser/logout` |
| Account lifecycle | `POST /auth/register/` (email only), `/auth/verify-registration` (token plus password), `/auth/logout/`, `/auth/password-reset/request`, `/auth/password-reset/confirm`; `PATCH /auth/email` requires the current password |
| Current user | `GET/PATCH /users/me`, `PATCH /users/username`, `POST/DELETE /users/avatar` |
| Contacts | `GET/POST /orgs/{org_slug}/contacts/`, CRUD below `/contacts/{slug}/`, avatar upload/delete |
| Tags | list/create/search below `/orgs/{org_slug}/tags/`; assignment accepts up to 50 normalized names and targets are allowlisted |
| Images | media library and relation operations below `/orgs/{org_slug}/images/` |
| Public shares | `POST /shared/images/resolve/` with the raw token in the body |
| Exports | `GET/POST /orgs/{org_slug}/exports/`, status/download and retry by job UUID |

All paths in the table are relative to `/api/v1`. Authenticated routes accept
`Authorization: Bearer <access-token>`.

Browser login and registration return an access token but keep the rotating
refresh token in an HttpOnly cookie. Browser state-changing auth requests require
the CSRF token returned by `/auth/browser/csrf`; see [security.md](security.md).

Export creation returns a job, not a URL. Poll the authenticated job route; a
ready response contains a short-lived signed download URL. Export files expire
after `EXPORT_RETENTION_DAYS` and the maintenance task deletes the object.
