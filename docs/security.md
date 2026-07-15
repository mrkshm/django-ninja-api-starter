# Authentication and security

## Sessions

Login creates a database-backed device session plus a five-minute access token
and a 30-day refresh token. Refresh rotates and blacklists the old token. Replay
revokes the associated device session. Logout takes the current refresh token
and revokes it; logout-all, password reset, deactivation, and account deletion
invalidate relevant sessions through `auth_version` and session state.

JWTs use HS256 with an issuer, audience, and a signing key independent from
Django's `SECRET_KEY`. To rotate normally, deploy support for both old and new
keys before issuing with the new key; this starter's single-key configuration
instead requires all users to sign in again. For emergency revocation, replace
the signing key, increment every active user's `auth_version`, revoke active
sessions, and restart web/workers.

## Client storage

iOS clients keep the refresh token in Keychain with an accessibility class
appropriate to the app and keep access tokens in memory. Never place tokens in
UserDefaults, logs, analytics, crash metadata, URLs, or backups.

The JSON refresh-token API is acceptable for trusted native clients. A browser
must not persist it in localStorage. Before shipping a browser client, add a
dedicated same-site backend flow using a `Secure`, `HttpOnly`, suitable
`SameSite` refresh cookie plus CSRF protection; keep the access token in memory.
Production CORS does not allow credentials by default.

Verification, email-change, and password-reset messages place tokens in URL
fragments so normal server access logs do not receive them. The client submits
the token to a POST body.

Registration proves email ownership before creating a user: `/auth/register/`
accepts only the email and creates a short-lived pending identity. The client
submits the verification token together with the chosen password to
`/auth/verify-registration`; only then are the user and personal organization
created. Repeated requests rotate the pending token, and expired pending rows
can be deleted without leaving orphan accounts.

Requesting an email change requires the current password. The existing address
receives a security notice, the new address receives the verification link, and
both addresses are notified after completion. Pending changes are bound to the
user's `auth_version`, so changing/resetting the password or otherwise revoking
all sessions invalidates an outstanding email-change token.

## Tenant roles

- `member`: view and CRUD ordinary contacts, tags, private images, and relations.
- `admin`: member abilities plus export and organization-management operations.
- `owner`: admin abilities and ownership-level destructive operations.
- platform admin: Django superuser only; `is_staff` alone does not bypass tenant
  policy.

Cross-tenant object access is hidden as `404`. Every polymorphic target is
allowlisted; arbitrary Django models cannot be resolved from client input.

## Media

General images and exports are private. URLs are signed only after authorization
and use short lifetimes/private cache directives. Share tokens are random,
stored only as hashes, returned once, expire, can be revoked, and are submitted
to a throttled POST endpoint rather than embedded in request paths.

User and contact avatars are public to everyone by design. They are normalized
WebP files with stripped metadata and unguessable keys under
`public/avatars/users/` or `public/avatars/contacts/` in a dedicated public
bucket. Public bucket permissions must never include private image/export keys.

## Logging

Logs contain request IDs and security event names, not authorization headers,
cookies, passwords, raw tokens, email bodies, storage credentials, or signed
URLs. Validation input values are omitted. Restrict log access and retain logs
for the shortest period that meets operational/legal needs (30 days is a useful
starting point). Connect an error provider at `core.error_reporting` and apply
the same redaction rules.
