# Production hardening checklist

This is the completed implementation record for the fresh-start template. A
derived application is not automatically production-ready: the final operator
exercise at the end must be run against that application's real providers and
deployment target.

## Architecture decisions

- [x] Fresh starter; no route, data, or migration backward compatibility.
- [x] Native iOS is the primary client; web is secondary.
- [x] The starter owns email/password authentication.
- [x] Members CRUD ordinary tenant content; admin/owner protect management,
  export, and organization-level destructive actions.
- [x] Tenant routes use `/api/v1/orgs/{org_slug}/<resource>/...`.
- [x] User and contact avatars are public; every other media class is private.
- [x] Unattached images are persistent media-library objects.
- [x] Manual single-server Docker Compose is the supported deployment example.
- [x] Standard PostgreSQL is the default; PostGIS is opt-in.

## Reproducible foundation

- [x] Base, development, test, CI, and fail-fast production settings are split.
- [x] Explicit settings select test/CI services; tests cannot discover production
  through `pytest` process inspection.
- [x] Initial application migrations are committed and checked for drift.
- [x] CI migrates an empty PostgreSQL database and applies migrations twice.
- [x] Python and all runtime/dev dependencies are locked with uv.
- [x] Python/uv/container/service images and GitHub actions are pinned.
- [x] Dependabot updates Python, Docker, and action dependencies weekly.
- [x] CI audits Python dependencies, scans the image, and scans Git history for
  secrets.
- [x] Environment templates use consistent neutral names.

## Authentication and account lifecycle

- [x] Five-minute access and 30-day refresh policy, issuer/audience, and a JWT key
  independent from Django's secret are explicit.
- [x] Refresh tokens rotate, are blacklisted after rotation, and reject replay.
- [x] Database-backed device sessions support current-device and all-device
  revocation.
- [x] Logout, password change/reset, deactivation, and deletion invalidate the
  documented sessions; access tokens carry `auth_version`.
- [x] Expired token/session cleanup is scheduled and idempotent.
- [x] Password validators run at every password-setting endpoint.
- [x] Email identity is normalized and case-insensitively unique in PostgreSQL.
- [x] Login uses Django authentication and rejects inactive users.
- [x] Login, registration, resend, refresh, reset, and public share resolution
  are throttled and security events are audited without secret values.
- [x] The single-Caddy proxy count is explicit; real throttle tests cover cache
  windows, IP/user identity, independent scopes, and 429 responses without a
  global bypass.
- [x] Account-existence responses are generic where enumeration is relevant.
- [x] Verification/reset/email-change tokens are hashed at rest, single-use,
  expiring, delivered asynchronously, and submitted by POST body.
- [x] Registration creates only a pending email identity; the user and personal
  organization are created after token verification and password validation.
- [x] Email changes require the current password, notify the old and new
  addresses, bind to `auth_version`, and revoke all sessions on completion.
- [x] Native Keychain guidance and a separate browser cookie/CSRF flow
  design are documented.

## Tenant and model integrity

- [x] Personal-organization creation and account deletion use explicit atomic
  services.
- [x] Deleting a member cannot delete an organization owned by someone else.
- [x] Contacts, tags, images, relations, and exports resolve through an authorized
  organization scope before object lookup.
- [x] Contact slugs are unique per organization and duplicate local slugs across
  tenants are supported.
- [x] Request schemas cannot move a resource to another organization.
- [x] Member/admin/owner/platform-admin behavior is centralized and tested.
- [x] Members are explicitly editor-level collaborators; creator ownership does
  not silently restrict ordinary organization content.
- [x] Group organizations retain at least one active owner through transactional
  membership/account services and deferred PostgreSQL constraint triggers.
- [x] Each creator has one personal organization and an immutable creator-owner
  membership, enforced through services, a conditional constraint, and a
  deferred PostgreSQL guard.
- [x] Cross-tenant platform-admin access emits structured audit events without
  tenant payload data.
- [x] Username availability requires authentication and has a dedicated throttle.
- [x] Contact resource responses expose public avatar URLs directly; redundant
  unauthenticated avatar URL helper routes have been removed.
- [x] Platform administration requires superuser; staff is not a tenant bypass.
- [x] Named constraints enforce tenant uniqueness, role/type values, and relation
  invariants; tenant query paths have indexes.
- [x] Nullable text handling is consistent and uniqueness races are converted
  from database `IntegrityError` to stable `409` responses.
- [x] Polymorphic tags/images accept only explicit models with a verified
  organization relationship.

## Media and external consistency

- [x] Uploaded bytes are decoded; byte, pixel, dimension, and decompression-bomb
  limits are enforced.
- [x] EXIF orientation is applied and output is normalized to WebP without source
  metadata.
- [x] Private keys use an unguessable tenant namespace; avatars use random keys
  in a dedicated public bucket/namespace.
- [x] Public avatar URLs work without membership and cannot address private media.
- [x] Partial multi-object uploads are compensated if processing or database
  creation fails.
- [x] Deletion commits database state first and schedules external deletion with
  `transaction.on_commit`; failures are visible and reconcilable.
- [x] Variants succeed together or the upload fails and cleans up.
- [x] Share tokens are hashed, expiring, revocable, returned only at creation,
  and resolved through a throttled POST body.
- [x] Private signed URLs have short lifetimes and private cache behavior.
- [x] Unattached media is never deleted merely for lacking a relation.
- [x] `audit_media` provides dry-run reconciliation and explicit age-gated cleanup
  of genuinely unreferenced private objects.

## Background work and exports

- [x] Celery uses JSON, late acknowledgement, worker-loss rejection, bounded
  prefetch, hard/soft time limits, expiring nonsensitive results, and separated
  email/export/maintenance queues.
- [x] Request IDs propagate into published Celery tasks and worker log context.
- [x] Email retries transient failure, publication failure is observable, and no
  complete email body or token is logged.
- [x] Export jobs persist requester, organization, status, timestamps, object
  key, expiry, and a safe error state.
- [x] Only admin/owner may create, inspect, download, or retry an export.
- [x] Archives spool to disk and stream media rather than accumulating the whole
  ZIP in memory.
- [x] Celery stores/returns job IDs, never signed download URLs.
- [x] Authenticated retrieval creates a five-minute URL; the scheduled retention
  task deletes expired export objects.
- [x] Failed exports are visible and safely retryable; exports are explicitly
  portability archives, not database backups.
- [x] Export execution holds a whole-job PostgreSQL advisory lock, replaces a
  deterministic object key, compensates failed finalization, and records worker
  heartbeats and attempt counts.
- [x] Beat requeues stale pending/processing exports; failed or stale jobs may be
  retried, fresh active jobs retain ownership, and terminal jobs are no-ops on
  duplicate delivery.

## API structure and reliability

- [x] Domain API modules bind transport while services own critical state
  transitions; organization policy remains centralized.
- [x] Global validation/HTTP/unhandled error behavior lives in `core` and never
  echoes submitted values or internal exceptions.
- [x] Account email normalization/validation is shared; generic recovery and
  resend endpoints retain indistinguishable malformed/unknown responses.
- [x] Contact inputs mirror database column limits, validate optional email,
  and cap free-form notes before persistence.
- [x] Contact POST returns 201, PUT fully replaces/reset omitted fields, PATCH is
  partial, and user/organization/contact routing slugs remain stable after edits.
- [x] Contact search length/term count and sort field/order are explicit API
  constraints; invalid query parameters are rejected rather than corrected.
- [x] Contact sorting uses organization-prefixed indexes; response serializers
  receive selected/prefetched relationships and have query-count regression tests.
- [x] Contact search has a dedicated authenticated-user throttle that does not
  penalize ordinary list requests.
- [x] Export collection responses contain metadata only; a short-lived download
  credential is generated only when an authorized client fetches one job.
- [x] Avatar reads are size-bounded before allocation; all accepted image input
  types receive pixel/dimension checks without process-global Pillow mutation.
- [x] Email tasks retry transient transport failures only and explicitly document
  SMTP's at-least-once/possible-duplicate semantics.
- [x] Correlation IDs are accepted only in a safe format, generated otherwise,
  returned to clients, and included in logs.
- [x] Idempotency hashes normalized JSON/file metadata, uses transaction-scoped
  PostgreSQL locks, and commits each database mutation with its durable replay
  response. Changed payloads/in-progress work are rejected and expired records
  are cleaned on schedule.
- [x] The generated OpenAPI document is committed and CI fails on drift.

## CI and verification

- [x] SQLite remains the fast unit-test default; the CI suite runs on PostgreSQL
  with Redis-backed cache/throttling support.
- [x] Regression coverage includes tenant isolation, deletion invariants, token
  rotation/replay/revocation, password validation, publication failures, upload
  rollback, media reconciliation, idempotency mismatch, throttle identity/rate
  enforcement, and export locking/recovery lifecycle.
- [x] CI runs Black, high-signal Flake8, mypy, pytest, migration checks, Django
  checks, OpenAPI diff, dependency audit, production `check --deploy`, image
  build/scan, and a container liveness smoke test.
- [x] Tests use storage/email contract fakes; the final release exercise requires
  real S3-compatible and captured SMTP services.

## Deployment and operations

- [x] Caddy terminates TLS, replaces forwarded scheme information, redirects
  HTTP, and limits request bodies.
- [x] Production sets secure cookies, strict hosts/CORS, HSTS, content sniffing,
  and framing protections and has no `unsafe-eval` CSP source.
- [x] Redis is password-protected and reachable only on the private network.
- [x] Liveness is downstream-free; readiness checks PostgreSQL and cache.
- [x] Web/worker/beat run non-root with read-only roots, dropped capabilities,
  no-new-privileges, tmpfs scratch space, and graceful shutdown time.
- [x] Gunicorn worker/thread/timeouts are environment-bounded rather than derived
  from host CPU count.
- [x] Migrations are a one-off release step and workers start only afterward.
- [x] Rollback and expand/migrate/contract behavior are documented.
- [x] Provider-neutral error reporting has one integration boundary.
- [x] Required metrics, alerts, log retention/access, queue/task inspection, and
  synthetic provider checks are documented.
- [x] Encrypted PostgreSQL backup and restore scripts plus off-host retention,
  RPO/RTO, Redis expectations, object versioning, and quarterly restore drills
  are documented.
- [x] JWT key, storage credential, and tenant deletion incident runbooks exist.

## Starter quality

- [x] Clean-clone quickstart and verification commands are in the README.
- [x] `seed_demo` is idempotent and refuses to run without `DEBUG=True`.
- [x] Architecture, API, security, environment, deployment, operations, PostGIS,
  and upgrade policy documentation matches current behavior.
- [x] Stale Kamal, PostGIS-default, old-route, stateless-logout, and compliance
  claims have been removed.
- [x] Public avatar visibility and private-media boundaries are explicit.

## Final operator release gate

Run this for every derived product in an isolated production-like environment.
These remain unchecked in the template because provider credentials, DNS, and a
backup destination are intentionally not committed.

- [ ] Clone into a clean environment and configure only from the documented
  templates/secret mechanism.
- [ ] Build and scan the pinned production image; provision empty PostgreSQL,
  Redis, captured SMTP, and S3-compatible private/public buckets.
- [ ] Apply migrations, then start web, worker, beat, and Caddy.
- [ ] Register/verify/login; rotate and replay a refresh token; logout; reset the
  password and prove old sessions are invalid.
- [ ] Exercise two tenants and prove cross-tenant isolation for contacts, tags,
  images, relations, avatars, shares, and exports.
- [ ] Exercise public avatars and private signed media; expire/revoke a share.
- [ ] Generate, retrieve, retry, and expire an export.
- [ ] Confirm logs/task results contain no credentials, raw tokens, email bodies,
  or complete signed URLs.
- [ ] Run the complete CI workflow and production `check --deploy` without
  unexplained warnings.
- [ ] Create an encrypted backup, restore it into isolation, reconcile stored
  media, and record achieved RPO/RTO.
- [ ] Verify dashboards, alerts, worker/beat absence detection, SMTP delivery,
  storage versioning/lifecycle, and incident contacts.
