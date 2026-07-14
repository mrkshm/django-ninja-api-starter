# Production Readiness and Hardening Checklist

This document is the implementation roadmap for turning this repository into a production-ready Django Ninja starter template.

It is intentionally stricter than a feature checklist. A starter should be safe and reproducible for a new project deployed from a fresh clone, not merely functional in an existing development environment.

## How to use this checklist

- Complete the phases in order unless an item explicitly has no dependency on an earlier phase.
- Prefer small, reviewable commits grouped by one concern.
- Add or update tests with every behavioral change.
- Do not mark an item complete until its acceptance criteria pass.
- Preserve backwards compatibility only when it is an explicit product requirement. This is a starter template, so correcting poor contracts is preferable to carrying permanent compatibility code.

Priority meanings:

- **P0 — release blocker:** unsafe or unable to deploy reliably.
- **P1 — production requirement:** must be complete before public production use.
- **P2 — hardening:** strongly recommended for a reusable production starter.
- **P3 — polish:** improves maintainability or developer experience.

## Settled architecture decisions

- This is a fresh starter. Backwards compatibility with previous routes, schemas, migrations, or deployments is not required.
- Clients are primarily native iOS applications and secondarily web applications.
- Native clients use short-lived JSON access tokens and rotating refresh tokens stored in iOS Keychain.
- The starter owns email/password authentication; external OIDC providers remain optional extensions.
- Organization members may create, update, and delete ordinary organization content. Admin/owner roles protect membership, export, organization-management, and destructive organization-level operations.
- Tenant routes use the consistent `/api/v1/orgs/{org_slug}/<resource>/...` shape.
- Unattached images are persistent media-library assets, not cleanup candidates merely because they have no relation.
- User and contact avatars are intentionally public. Public avatar keys must remain isolated from private media namespaces and must not grant access to other objects.
- General private images use authorized signed URLs. Explicit share links are revocable and expire.
- Production deployment targets a documented single-server Docker Compose topology; Kamal is not a supported path.
- Cloudflare R2 is supported through provider-neutral S3-compatible storage configuration.
- Standard PostgreSQL is the default. PostGIS is opt-in and documented separately.

## Production-ready definition

The starter is production-ready when all of the following are true:

- [ ] A fresh clone can create its environment, database, and application schema using documented commands.
- [ ] The same pinned dependency set is used locally, in CI, and in container builds.
- [ ] Production refuses to start with missing or insecure mandatory configuration.
- [ ] Passwords, reset links, verification tokens, JWTs, storage credentials, and signed URLs are never written to logs.
- [ ] Authentication supports rotation, revocation, meaningful logout, and security-event session invalidation.
- [ ] Tenant data is consistently scoped and protected at routing, query, service, and database levels.
- [ ] Database changes and external side effects have defined failure and recovery behavior.
- [ ] The application has production checks, monitoring hooks, backups, and documented recovery procedures.
- [ ] CI proves migrations, tests, static analysis, production checks, and a container smoke test.
- [ ] Documentation matches the actual registered API and deployment behavior.

---

## Phase 0 — Establish a safe baseline

### Repository and change discipline — P0

- [ ] Keep this hardening work isolated on a dedicated branch.
- [ ] Record the current API schema before changing routes or response contracts.
- [ ] Record the current full test result as the behavioral baseline.
- [ ] Decide whether compatibility with existing deployments/data is required.
- [ ] If existing data must survive, take and verify a database and object-storage backup before changing models.

Acceptance criteria:

- [ ] `pytest -q` passes before the first behavior-changing commit.
- [ ] The generated OpenAPI schema is stored or diffable in CI.
- [ ] The migration strategy explicitly states either "fresh starter only" or "upgrade existing installations."

---

## Phase 1 — Make fresh deployment reliable

### Commit application migrations — P0

- [ ] Remove the global `migrations/` rule from `.gitignore`.
- [ ] Generate and commit initial migrations for `accounts`, `organizations`, `contacts`, `tags`, and `images`.
- [ ] Review migration dependencies, constraints, indexes, defaults, and callable serialization.
- [ ] Add a CI check using `makemigrations --check --dry-run`.
- [ ] Test migrating an empty PostgreSQL database from zero.
- [ ] Test applying migrations twice to prove repeatability.

Acceptance criteria:

- [ ] A fresh database obtains every application table using `python manage.py migrate` without `--run-syncdb`.
- [ ] `python manage.py makemigrations --check --dry-run` exits successfully without proposed changes.

### Split settings by environment — P0

- [ ] Introduce clear base, development, test, and production settings modules.
- [ ] Remove test detection based on whether `pytest` appears in `sys.modules`.
- [ ] Use an explicit test settings module in `pytest.ini`.
- [ ] Centralize environment parsing and document every supported variable.
- [ ] Fail fast in production when required database, Redis, email, storage, host, frontend, or signing configuration is missing.
- [ ] Fix eager evaluation of the `R2_PRIVATE_BUCKET_NAME` fallback.
- [ ] Decide whether a public bucket is mandatory; make it optional if public images are optional.
- [ ] Remove unused, duplicated, or misleading environment variables.
- [ ] Ensure `env.example`, Docker Compose, Kamal configuration, and settings use identical names.

Acceptance criteria:

- [ ] Development can boot with documented local defaults.
- [ ] Tests cannot connect to production services accidentally.
- [ ] Production startup fails with a clear message for every missing mandatory secret or endpoint.

### Pin and reproduce dependencies — P0

- [ ] Choose a dependency workflow: lock file, compiled requirements, or constraints file.
- [ ] Pin Django, Django Ninja, Ninja Extra, Ninja JWT, Celery, Redis, Pydantic, Pillow, boto3, database drivers, and tooling.
- [ ] Separate runtime dependencies from development/test dependencies.
- [ ] Remove unused packages.
- [ ] Add an automated dependency update process.
- [ ] Add vulnerability scanning for Python dependencies and container images.
- [ ] Pin the container base image to a supported Python release and preferably an immutable digest.

Acceptance criteria:

- [ ] Two clean installations resolve the same versions.
- [ ] Local, CI, and container Python versions agree.
- [ ] Type checking no longer fails because of an incompatible unpinned plugin combination.

### Repair email delivery — P0

- [ ] Configure Django's email backend from environment variables.
- [ ] Use one email-delivery abstraction for account emails and exports.
- [ ] Keep the console backend development-only.
- [ ] Configure sender address, TLS/SSL, timeouts, and provider credentials explicitly.
- [ ] Ensure worker logs never include complete email bodies containing tokens or signed links.
- [ ] Define retry behavior for transient provider failures.
- [ ] Decide what the API does when task publication fails.
- [ ] Add a production-like email integration test using a safe test provider or captured SMTP service.

Acceptance criteria:

- [ ] Registration verification and password-reset messages are delivered outside development.
- [ ] No live token or signed URL is present in application or Celery logs.
- [ ] Email-provider failure is observable and recoverable.

### Fix transport security and proxy trust — P0

- [ ] Terminate TLS in the documented deployment topology.
- [ ] Redirect HTTP to HTTPS at the proxy or Django layer.
- [ ] Configure `SECURE_PROXY_SSL_HEADER` only for a trusted, sanitizing proxy.
- [ ] Configure secure session and CSRF cookies where those Django features are used.
- [ ] Review HSTS, preload, allowed hosts, trusted CSRF origins, and CORS origins.
- [ ] Remove development origins from production CORS configuration.
- [ ] Remove `'unsafe-eval'` and minimize `'unsafe-inline'` in CSP, or document why API documentation requires them.
- [ ] Protect Redis with network isolation and authentication; use TLS where traffic leaves a trusted host/network.

Acceptance criteria:

- [ ] `python manage.py check --deploy` has no unexplained warnings.
- [ ] Plain HTTP cannot transmit credentials or bearer tokens in production.
- [ ] Spoofed forwarded headers cannot trick Django into treating an insecure request as secure.

---

## Phase 2 — Harden authentication and account lifecycle

### Explicit JWT policy — P0

- [ ] Add explicit Ninja JWT settings rather than relying on library defaults.
- [ ] Keep access tokens short-lived.
- [ ] Select and document the refresh-token lifetime and inactivity policy.
- [ ] Enable refresh-token rotation.
- [ ] Enable blacklisting after rotation.
- [ ] Install and migrate the Ninja JWT blacklist app.
- [ ] Schedule expired outstanding/blacklisted-token cleanup.
- [ ] Use a JWT signing key independent from Django's `SECRET_KEY`.
- [ ] Configure and validate issuer and audience.
- [ ] Document signing-key rotation and emergency revocation.

Acceptance criteria:

- [ ] A refresh token succeeds once and fails after it has been rotated.
- [ ] Replaying an old refresh token cannot create another access token.
- [ ] JWT configuration is covered by settings tests.

### Meaningful logout and session invalidation — P0

- [ ] Require logout to identify and revoke the current refresh token/session.
- [ ] Revoke all relevant refresh sessions after password reset.
- [ ] Define whether password change revokes the current session, other sessions, or all sessions.
- [ ] Revoke sessions when a user is deactivated or deleted.
- [ ] Consider a user/session `token_version` claim if immediate access-token invalidation is required.
- [ ] Ensure refresh validates current user existence, active status, and token/session version.
- [ ] Add "log out all devices" support or document why it is not included.

Acceptance criteria:

- [ ] Revoked refresh tokens cannot be used after logout, password reset, or account deactivation.
- [ ] Tests explicitly cover current-session and all-session policies.

### Credential validation and abuse protection — P0

- [ ] Call Django's password validators during registration, password change, and password reset.
- [ ] Normalize email addresses consistently before lookup and persistence.
- [ ] Enforce case-insensitive email uniqueness at the database level if email identity is case-insensitive.
- [ ] Use Django authentication backends or reproduce their active-user policy deliberately.
- [ ] Rate-limit login, registration, verification resend, refresh, password-reset request, and password-reset confirmation.
- [ ] Choose rate-limit keys that resist distributed attacks while avoiding easy denial of service against one account.
- [ ] Keep account-existence responses and meaningful timing as uniform as practical.
- [ ] Add audit events for login success/failure, reset, password change, logout, and revocation without logging credentials or tokens.

Acceptance criteria:

- [ ] Weak passwords are rejected consistently by every password-setting endpoint.
- [ ] Inactive users cannot receive usable token pairs.
- [ ] Authentication throttling is tested with throttling enabled.

### Browser/mobile token handling — P1

- [ ] Define supported client types and their token-storage threat models.
- [ ] For browser clients, prefer an in-memory access token and a `Secure`, `HttpOnly`, appropriately `SameSite` refresh cookie with CSRF protection.
- [ ] If refresh tokens remain in JSON, explicitly document secure storage requirements and XSS implications.
- [ ] For native clients, document OS secure-storage expectations.
- [ ] Ensure CORS credential behavior matches the selected browser design.

---

## Phase 3 — Protect tenant and domain integrity

### Replace destructive organization signals — P0

- [ ] Fix user deletion so it cannot delete every personal organization in which the user is merely a member.
- [ ] Define ownership and deletion invariants for personal organizations.
- [ ] Move user onboarding/personal-organization creation into an explicit transactional service.
- [ ] Move destructive account/organization deletion into explicit services.
- [ ] Decide what happens to shared organizations, memberships, content, and creator fields when a user is deleted.
- [ ] Add tests with multiple users and memberships around every deletion path.

Acceptance criteria:

- [ ] Deleting a member cannot delete another user's organization or data.
- [ ] User and personal-organization creation cannot be partially committed.

### Normalize organization-scoped routes and queries — P1

- [ ] Adopt one route convention, preferably `/orgs/{org_slug}/<resource>/...`.
- [ ] Remove duplicated segments such as `/orgs/orgs/{org_slug}/export/`.
- [ ] Move contacts under explicit organization scope or define an intentional cross-organization aggregate endpoint.
- [ ] Scope contact identity by `(organization, slug)` rather than a global slug where appropriate.
- [ ] Fetch tenant-owned objects through already-scoped querysets instead of fetching globally and authorizing afterward.
- [ ] Decide whether unauthorized object access returns `403` or hides existence with `404`, then apply consistently.
- [ ] Add route-level integration tests through the assembled API, not only direct function tests.

Acceptance criteria:

- [ ] Two organizations can safely use the same local resource slug where the domain permits it.
- [ ] Cross-organization reads and writes are rejected in integration tests.
- [ ] The documented export route equals the OpenAPI route and the real request route.

### Strengthen model constraints — P1

- [ ] Replace `unique_together` with named `UniqueConstraint` declarations.
- [ ] Add indexes for common tenant-scoped lookups and ordering.
- [ ] Add constraints for organization type, membership roles, and personal-organization ownership invariants where practical.
- [ ] Review nullable-plus-blank string fields and standardize null handling.
- [ ] Handle uniqueness races using database constraints and `IntegrityError`, not only preflight `.exists()` checks.
- [ ] Run constraint and concurrency tests against PostgreSQL.

### Bound polymorphic relationships — P1

- [ ] Define an allowlist of models that may receive polymorphic tags and images.
- [ ] Validate that every allowed model has a reliable organization relationship.
- [ ] Prevent clients from resolving arbitrary installed models by app/model name.
- [ ] Define orphan detection and cleanup for generic relations.
- [ ] Consider explicit relation models if the starter only needs a small fixed set of attachable resources.

---

## Phase 4 — Make storage and media workflows recoverable

### Upload validation — P1

- [ ] Validate decoded image content, not only MIME prefixes and filename extensions.
- [ ] Enforce pixel/dimension and decompression-bomb limits.
- [ ] Normalize output formats and strip unsafe/unneeded metadata.
- [ ] Centralize user, contact, and general image validation and size configuration.
- [ ] Avoid returning raw exception messages to clients.

### Database/object-storage consistency — P1

- [ ] Define the commit order for database records and storage objects.
- [ ] Delete newly uploaded objects when later processing or database creation fails.
- [ ] Ensure database deletion failure cannot silently leave the application pointing at deleted objects.
- [ ] Make variant generation failure explicit: retry, mark processing state, or fail the upload and clean up.
- [ ] Track processing status if variants are generated asynchronously.
- [ ] Use `transaction.on_commit` where external work should happen only after a successful database commit.
- [ ] Add reconciliation commands for missing database records, missing objects, and unreferenced objects.

### Media authorization — P1

- [ ] Serve intentionally public user/contact avatars from a dedicated public namespace or bucket without exposing private media.
- [ ] Use unguessable, non-sensitive avatar object keys and return stable public URLs with appropriate cache headers.
- [ ] Hash image share-link tokens at rest and reveal the raw token only at creation.
- [ ] Define revocation, expiration, and maximum lifetime for share links.
- [ ] Rate-limit public share-link resolution.
- [ ] Ensure signed URLs have the minimum useful lifetime and correct private cache headers.
- [ ] Never log complete signed URLs or bearer share tokens.

### Cleanup safety — P1

- [ ] Decide whether unattached images are legitimate media-library items or disposable temporary uploads.
- [ ] Add an age/grace-period condition before deleting unattached images.
- [ ] Ensure cleanup cannot delete an image while an attach operation is in progress.
- [ ] Include all token types, including expired pending registrations, in cleanup policy.
- [ ] Make cleanup tasks idempotent and observable.
- [ ] Add dry-run management commands before enabling destructive scheduled cleanup.

---

## Phase 5 — Make background work production-safe

### Celery configuration — P1

- [ ] Configure task hard and soft time limits.
- [ ] Configure acknowledgement and worker-loss behavior intentionally.
- [ ] Define retry policies per task rather than relying on one generic pattern.
- [ ] Ensure tasks are idempotent before enabling automatic retries.
- [ ] Add queue separation or routing for email, media, cleanup, and large exports if workloads differ.
- [ ] Set result expiration and avoid storing sensitive task results.
- [ ] Add worker and beat health monitoring.
- [ ] Document how failed tasks are inspected and replayed.

### Organization export — P1

- [ ] Fix and integration-test the registered export route.
- [ ] Introduce an export-job model with requester, organization, status, timestamps, object key, expiry, and error state.
- [ ] Avoid returning or persisting complete signed URLs in Celery results.
- [ ] Stream or spool large exports instead of holding the complete archive in memory.
- [ ] Prevent spreadsheet/formula injection if CSV output is later added.
- [ ] Enforce export-object retention with an R2/S3 lifecycle rule or a tested cleanup task.
- [ ] Confirm exports include all required organization data and relationship metadata.
- [ ] Document whether the export is portability-focused, backup-focused, or intended to satisfy a specific privacy request.

Acceptance criteria:

- [ ] A failed export is visible and can be retried safely.
- [ ] Export objects are actually deleted after the declared retention period.
- [ ] Only authorized organization admins can create and retrieve exports.

---

## Phase 6 — Improve API and code structure

### Thin endpoint modules — P2

- [ ] Keep request parsing, schema binding, and response mapping in API modules.
- [ ] Move state-changing workflows into per-domain `services.py` modules.
- [ ] Move reusable read/scoping logic into `selectors.py` or custom querysets/managers.
- [ ] Keep authorization policy centralized in the organizations domain.
- [ ] Avoid a generic repository layer unless it solves a demonstrated problem.
- [ ] Replace critical hidden signal behavior with explicit service calls.

Suggested application shape:

```text
app/
  api.py          # transport and endpoint declarations
  schemas.py      # request and response contracts
  models.py       # persistence and local invariants
  services.py     # state-changing workflows
  selectors.py    # reusable scoped reads
  tasks.py        # asynchronous entry points calling services
  tests/
```

### Shared API behavior — P2

- [ ] Move global validation/error handling out of the `images` application.
- [ ] Define one consistent error envelope and status-code policy.
- [ ] Reuse shared response schemas instead of duplicating `DetailResponse` variants.
- [ ] Standardize trailing slash, pagination, filtering, ordering, and bulk-operation conventions.
- [ ] Return stable public error messages while logging internal exceptions with correlation IDs.
- [ ] Version intentional breaking API changes.

### Robust idempotency — P2

- [ ] Hash the normalized request body and relevant content metadata with each idempotency key.
- [ ] Reject reuse of a key with a different request.
- [ ] Reserve in-progress operations atomically.
- [ ] Prevent concurrent requests with the same key from both executing.
- [ ] Define which response classes are cached.
- [ ] Define TTL, retry, and abandoned-operation behavior.
- [ ] Add PostgreSQL/Redis concurrency tests.

---

## Phase 7 — Testing and continuous integration

### Test environments — P0/P1

- [ ] Keep fast SQLite tests only where database-specific behavior is irrelevant.
- [ ] Add a PostgreSQL/PostGIS integration test job.
- [ ] Run migrations normally in at least one test job.
- [ ] Test Redis-backed cache, throttling, and Celery task publication without globally bypassing them.
- [ ] Add storage contract tests against an S3-compatible test service where useful.
- [ ] Add SMTP integration coverage for transactional email.

### Critical regression tests — P0/P1

- [ ] Fresh migration from an empty database.
- [ ] OpenAPI and real-route smoke tests.
- [ ] Cross-organization access matrix for every tenant-owned resource.
- [ ] User/member/owner deletion scenarios.
- [ ] Refresh rotation, replay rejection, logout, and password-reset revocation.
- [ ] Password validation on all password-setting endpoints.
- [ ] Email failure and task-publication failure.
- [ ] Upload rollback and storage reconciliation.
- [ ] Cleanup grace periods and concurrent attachment.
- [ ] Idempotency concurrency and payload mismatch.
- [ ] Export authorization, failure, retry, and retention.

### CI pipeline — P0

- [ ] Run formatting/lint checks.
- [ ] Run type checking with a known-compatible pinned toolchain.
- [ ] Run unit tests.
- [ ] Run PostgreSQL integration tests.
- [ ] Run `makemigrations --check --dry-run`.
- [ ] Run `check --deploy` under production-like settings.
- [ ] Build the production container.
- [ ] Start the container and perform health/API smoke tests.
- [ ] Scan dependencies and the container image.
- [ ] Prevent secrets from being committed with secret scanning.

---

## Phase 8 — Observability and operations

### Logging and error reporting — P1

- [ ] Use structured logs consistently across web and worker processes.
- [ ] Add request/correlation IDs and propagate them into Celery tasks.
- [ ] Add an error-reporting provider hook without coupling the starter to one vendor.
- [ ] Redact authorization headers, cookies, passwords, tokens, email bodies, signed URLs, and storage credentials.
- [ ] Define auditable security events separately from verbose application logs.
- [ ] Set log retention and access controls appropriate to potentially sensitive metadata.

### Metrics and health — P1

- [ ] Keep a cheap liveness endpoint that does not depend on downstream systems.
- [ ] Add a readiness endpoint/check for database connectivity and required service configuration.
- [ ] Monitor API latency/error rates, authentication failures, throttling, Celery queue depth, task failures, email failures, and storage failures.
- [ ] Alert on worker/beat absence and repeated cleanup/export failure.

### Backup and recovery — P0/P1

- [ ] Configure automated PostgreSQL backups with encryption and retention.
- [ ] Configure object-storage versioning/retention as appropriate.
- [ ] Document Redis persistence expectations; do not treat cache/broker data as the system of record.
- [ ] Test database restoration.
- [ ] Test restoration or reconciliation of stored media.
- [ ] Document recovery point and recovery time objectives.
- [ ] Create an incident runbook for compromised JWT signing keys, leaked storage credentials, and accidental tenant deletion.

### Deployment behavior — P1

- [ ] Run migrations as a controlled release step, not concurrently from every web instance.
- [ ] Ensure workers start only after compatible migrations are applied.
- [ ] Use graceful Gunicorn and Celery shutdown settings.
- [ ] Choose Gunicorn worker counts from container CPU/memory limits rather than host `cpu_count()` alone.
- [ ] Configure request/body size limits at both proxy and application layers.
- [ ] Define rollback behavior for code and forward-only database migrations.
- [ ] Run services as non-root with a read-only filesystem where practical.

---

## Phase 9 — Documentation and starter quality

### Accurate documentation — P1

- [ ] Generate or verify route documentation against OpenAPI.
- [ ] Correct Swagger/OpenAPI URLs and every route prefix.
- [ ] Remove claims such as "GDPR-compliant" unless the implemented behavior and operating instructions support them.
- [ ] Document actual export retention enforcement.
- [ ] Document authentication/session behavior and client token storage.
- [ ] Document tenant roles and the exact permissions of member, admin, owner, and platform admin.
- [ ] Document storage visibility, signed URLs, share links, and cleanup rules.
- [ ] Document required infrastructure and production environment variables.

### Starter ergonomics — P2/P3

- [ ] Provide a verified quickstart that works from a clean clone.
- [ ] Provide development fixtures or a safe seed command.
- [ ] Provide commands for tests, linting, type checking, migrations, workers, and production checks.
- [ ] Replace project-specific deployment identifiers and usernames with neutral placeholders.
- [ ] Decide whether PostGIS is truly required; use standard PostgreSQL if the starter has no GIS feature.
- [ ] Decide whether both Kamal files are needed and establish one supported deployment example.
- [ ] Add an architecture overview describing app responsibilities and dependency direction.
- [ ] Add an upgrade policy for Django and security-sensitive dependencies.

---

## Final release gate

Do not label the template production-ready until all P0 and P1 items are complete and the following release exercise succeeds:

- [ ] Clone the repository into a clean environment.
- [ ] Configure it using only the documented environment template and secret mechanism.
- [ ] Build the production container from pinned dependencies.
- [ ] Provision empty PostgreSQL, Redis, email test infrastructure, and S3-compatible storage.
- [ ] Apply committed migrations.
- [ ] Start web, worker, and beat services.
- [ ] Register and verify a user.
- [ ] Log in, rotate a refresh token, and log out.
- [ ] Create two organizations/users and verify cross-tenant isolation.
- [ ] Create, update, list, and delete contacts, tags, images, and relationships.
- [ ] Test private media, share-link creation, expiry, and revocation.
- [ ] Request and complete a password reset; verify old sessions are invalidated.
- [ ] Generate and retrieve an organization export.
- [ ] Exercise backup and restore.
- [ ] Confirm logs and task results contain no credentials, tokens, email bodies, or complete signed URLs.
- [ ] Run the complete CI pipeline successfully.
- [ ] Run `python manage.py check --deploy` successfully with no unexplained warnings.

## Recommended implementation order

1. Migrations and settings split.
2. Dependency pinning and CI production gates.
3. Email configuration and TLS/deployment correction.
4. JWT/session hardening and password validation.
5. Organization deletion safety and tenant-scoped routes.
6. Storage consistency, media authorization, and cleanup safety.
7. Background-job and export reliability.
8. API/service refactoring and robust idempotency.
9. PostgreSQL integration coverage, observability, backups, and final documentation audit.

This order deliberately makes the project deployable and secure before investing in architectural polish.
