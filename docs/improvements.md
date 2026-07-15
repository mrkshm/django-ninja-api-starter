# Future Refactor Improvements

This document is the implementation checklist for the next refactor pass. It
records the concrete risks found during review, the intended fixes, and the
tests that should prove them.

The starter is already structurally sound and does **not** need a rewrite. The
refactor should remain risk-first: fix demonstrated correctness, security, and
operational problems before introducing new architecture.

The design principles in [`styleguide.md`](./styleguide.md) guide the work, but
they are defaults rather than a reason to split files or add infrastructure for
its own sake.

**Status (2026-07-15): Phases 1–9 are complete.** The explicitly deferred
items remain optional future work.

## Working rules

- Preserve public API behavior unless a checklist item explicitly changes it.
- Make one independently reviewable commit per coherent slice.
- Move tested behavior instead of recreating it from memory.
- Prefer explicit functions and Django ORM operations over service classes or
  repository wrappers.
- Keep database transactions short and external storage/network calls visible.
- Add concurrency tests against PostgreSQL where correctness depends on locks,
  constraints, deferred triggers, or advisory locks.
- Follow the canonical database lock hierarchy defined below; do not let each
  operation invent its own row-lock order.
- Regenerate and review OpenAPI after every intentional contract change.
- Update this checklist when a decision changes.

### Canonical database lock order

Operations that lock more than one aggregate or row type must acquire locks in
this order:

```text
Organization → User → dependent rows
```

Dependent rows include memberships, auth sessions, and pending registration,
password-reset, and email-change records.

Rules:

- [x] Lock organizations first when an operation enforces an organization
  invariant.
- [x] Lock organizations in ascending primary-key order when more than one is
  involved.
- [x] Lock the user next when user state or credentials are involved.
- [x] Lock user-dependent rows only after the user.
- [x] Lock multiple rows of one type in ascending primary-key order.
- [x] If an operation needs a dependent row to discover the user or
  organization, perform an unlocked identity lookup, acquire canonical locks,
  then refetch and fully revalidate the dependent row under lock.
- [x] Prefer separate explicit locking queries over a `select_for_update()`
  join whose cross-table lock acquisition is difficult to see.
- [x] Document any unavoidable exception next to the operation and cover it
  with a PostgreSQL concurrency test.

## Priority summary

### Do first: demonstrated bugs and risks

- [x] Bound every image upload read.
- [x] Cap bulk image file count and aggregate input size.
- [x] Fingerprint multipart idempotency requests using file content.
- [x] Make password changes atomic with session revocation.
- [x] Make password-reset tokens concurrency-safe and single-use.
- [x] Enforce one coherent pending password-reset state per user.
- [x] Remove the unused and misleading `last_login` field.
- [x] Make inaccessible and nonexistent organization slugs indistinguishable.
- [x] Remove hidden pending-token hashing and unusable token defaults.

### Do next: simplify real duplication and strengthen assurance

- [x] Consolidate tenant scope and authorization helpers.
- [x] Remove dead wrappers and compatibility exports.
- [x] Include the project package in mypy and enable checking untyped bodies.
- [x] Add routed permission, multipart, and idempotency tests.
- [x] Move account transactions into one explicit operations module while
  implementing the credential fixes.
- [x] Add PostgreSQL and admin coverage for user-deletion ownership behavior.

### Do only if the code benefits while being changed

- [x] Move repeated image/tag mutation algorithms out of HTTP handlers.
- [x] Extract export archive construction from the Celery task module.
- [x] Reorganize test locations where ownership is currently misleading.

### Defer until a concrete requirement appears

- [ ] Transactional email outbox.
- [ ] Persistent image-upload state machine.
- [ ] Fine-grained organization-scoped Django admin for support staff.
- [ ] Further account/export package fragmentation.
- [ ] Purely aesthetic splitting of large test files.

---

## Completed hygiene

These findings were small enough to fix during review and are not part of the
future implementation workload.

- [x] Removed production Compose overrides that conflicted with Django's Celery
  soft and hard time-limit settings.
- [x] Made `wait_for_migrations` rebuild its migration executor on every poll,
  retry only operational database failures, and stop after a configurable
  timeout.
- [x] Added guarded email-template subject parsing and compiled-template
  caching.
- [x] Removed obsolete manipulation of Ninja's private `_registry` test state.
- [x] Added practical list/search configuration, `list_select_related`, and
  bounded FK widgets to the basic organization/contact/tag admins.
- [x] Made `Membership.__str__` use stored IDs instead of fetching related user
  and organization rows.
- [x] Reviewed Python 3.14 multi-exception syntax and retained Black 26's
  canonical formatting.

---

## Phase 1: Bound image uploads and fix multipart idempotency

This is the highest-priority phase. It contains a real memory-exhaustion
surface and an idempotency correctness gap.

### 1.1 Bound all image reads

Current behavior:

- Account and contact avatars use `read_uploaded_file_bounded`.
- `images/services.py:upload_image_file` still calls `file.read()` without a
  bound.
- The API checks the declared file size, but declared sizes can be absent or
  incorrect and do not make an unbounded read safe.

Implementation:

- [x] Define one authoritative accessor for `UPLOAD_IMAGE_MAX_BYTES`.
- [x] Reuse `read_uploaded_file_bounded` for the image library.
- [x] Prefer passing bounded bytes into `upload_image_file` so the operation's
  memory contract is explicit.
- [x] Preserve MIME-prefix checks as an early rejection only; Pillow content
  validation remains authoritative.
- [x] Return a stable 400 response for declared and streamed oversize failures.
- [x] Ensure an upload whose declared size exceeds the limit is never read.
- [x] Keep normalized/variant generation after the bounded read.

Tests:

- [x] A declared oversized image is rejected without calling `read()`.
- [x] An unknown-size oversized stream reads at most `max_bytes + 1`.
- [x] A dishonest declared size cannot bypass the bound.
- [x] Valid images still generate all expected variants.
- [x] Invalid content and decompression-bomb failures remain controlled 400s.

### 1.2 Cap bulk upload work

Current behavior:

- `images/api/uploads.py:bulk_upload_images` materializes and processes every
  submitted file.
- There is no explicit application-level count or aggregate-size limit.

Implementation:

- [x] Add `UPLOAD_IMAGE_MAX_FILES_PER_REQUEST`.
- [x] Add `UPLOAD_IMAGE_MAX_TOTAL_BYTES`.
- [x] Choose conservative starter defaults, for example 20 files and 50 MiB
  aggregate input, while retaining the per-file limit.
- [x] Reject excessive file count before processing any image.
- [x] Reject excessive declared aggregate size before processing.
- [x] Track bytes actually read so unknown or dishonest sizes cannot bypass the
  aggregate limit.
- [x] Document settings in `docs/environment.md` and the example environment.

Tests:

- [x] File count above the limit is rejected.
- [x] Declared aggregate size above the limit is rejected.
- [x] Actual aggregate bytes above the limit are rejected.
- [x] Exact boundary values are accepted.
- [x] Rejection performs no storage writes or image-row creation.

### 1.3 Fingerprint multipart content correctly

Current behavior:

- `core/utils/idempotency.py` attempts to fingerprint `request.body`.
- Bulk upload accesses `request.FILES` before calling `run_idempotently`.
- Once Django has parsed the multipart stream, reading `request.body` may fail;
  the fingerprint then falls back to an empty body.
- File fallback data contains only name, size, and MIME type.
- Different bytes with identical metadata can therefore replay the wrong
  result under the same idempotency key.

Recommended design:

- [x] Extend `run_idempotently` to accept an explicit request fingerprint or a
  bounded fingerprint callback.
- [x] Prepare bounded file content once, before the idempotent operation.
- [x] Hash field name, stable file order, normalized non-file values, file
  metadata, and file bytes.
- [x] Pass the digest to the idempotency layer without rereading the request
  stream.
- [x] Keep generic JSON fingerprint normalization for JSON endpoints.
- [x] Do not silently replace an unreadable body with an empty body when doing
  so weakens identity; use the explicit multipart path or return a controlled
  error.

Required semantics:

- [x] Same key and identical content replays the stored response.
- [x] Same key with different bytes returns 409 even when metadata matches.
- [x] Same content under a different key executes independently.
- [x] File ordering semantics are explicit and tested.
- [x] Fingerprinting never performs an unbounded read.

### 1.4 Keep cross-system cleanup proportionate

The database idempotency transaction cannot make S3 writes atomic. A database
failure after storage succeeds can leave unreferenced objects.

The risk is real, but a full persistent upload state machine is not justified
for the current synchronous starter.

Implement now:

- [x] Use storage keys that are traceable to an image/operation identifier.
- [x] Keep best-effort cleanup for known partial failures.
- [x] Add a focused test for a DB failure after storage writes.
- [x] Ensure the existing media audit reports unreferenced image keys.
- [x] Verify age-gated cleanup can safely remove those keys.
- [x] Document that Postgres and object storage are not one atomic system.

Do **not** add `pending`/`ready` upload state solely for theoretical atomicity.
Revisit a durable upload lifecycle if uploads become asynchronous, resumable,
or operational evidence shows meaningful orphan accumulation.

Acceptance criteria for Phase 1:

- [x] No image path performs an unbounded request-file read.
- [x] Bulk work has count and byte budgets.
- [x] Multipart retries distinguish actual content.
- [x] Known failures compensate; unknown orphans are reconcilable.
- [x] Routed multipart tests cover the real Ninja/Django stack.

---

## Phase 2: Make credential mutations atomic

Credential operations should own their complete transaction, including token
consumption and session invalidation.

Phase 2 introduces `accounts/operations.py` as the home for these use-cases.
Phase 9.1 later formalizes the boundary and moves other transaction workflows
only when doing so improves their implementation; Phase 9.1 is not a
prerequisite for this phase.

### 2.1 Atomic password change

Current behavior:

- `accounts/api.py:change_password` verifies and saves the password, then calls
  `revoke_all_sessions` separately.
- A failure between those operations can leave old sessions active after the
  password changes.

Implementation:

- [x] Add `change_password` to `accounts/operations.py`.
- [x] Lock the user row with `select_for_update()`.
- [x] Verify the current password against the locked row.
- [x] Validate the new password.
- [x] Save the password, revoke sessions, and increment `auth_version` in one
  transaction.
- [x] Emit the audit event only after the operation succeeds.
- [x] Keep request parsing and HTTP error/response mapping in `accounts/api.py`.

Tests:

- [x] Password update and session invalidation succeed together.
- [x] Simulated session-revocation failure rolls back the password.
- [x] Incorrect current password changes nothing.
- [x] Existing access and refresh tokens fail after success.

### 2.2 Atomic single-use password reset

Current behavior:

- `accounts/api.py:confirm_password_reset` reads the reset token without a row
  lock.
- Password update, session revocation, and token deletion are not one atomic
  transition.
- Concurrent requests can both pass validation and race to set different
  passwords.

Implementation:

- [x] Add `confirm_password_reset` to `accounts/operations.py`.
- [x] Hash the supplied token before lookup.
- [x] Read the pending row's `user_id` without locking only to discover lock
  identity.
- [x] Open one transaction and lock the user row first.
- [x] Refetch and lock the pending reset row after the user lock.
- [x] Revalidate the token hash, user relationship, and current pending state
  under lock.
- [x] Recheck expiry while holding the lock.
- [x] Validate and save the password.
- [x] Revoke all sessions and increment `auth_version`.
- [x] Delete the pending reset in the same transaction.
- [x] Return a small result or raise a domain error; map it to the stable API
  response at the boundary.

Tests:

- [x] A reset token succeeds once.
- [x] Reuse returns the generic invalid/expired response.
- [x] A PostgreSQL concurrency test proves only one simultaneous confirmation
  succeeds.
- [x] A failure during credential/session mutation leaves a consistent password
  and token state.

### 2.3 One pending reset per user

Current behavior:

- Reset request deletes existing rows and then creates a replacement without
  one transaction.
- `PendingPasswordReset` permits multiple rows per user under concurrency.

Recommended default:

- [x] Enforce one pending reset per user with a one-to-one relation or unique
  constraint.
- [x] Rotate the pending token with `update_or_create` in a transaction.
- [x] Treat concurrent reset requests as replacement of the same pending
  operation.
- [x] Preserve the enumeration-resistant generic response.
- [x] Ensure an old rotated link is invalid.

### 2.4 Make forced reauthentication explicit

Current behavior:

- Password change and completed email change revoke every device session,
  including the initiating session.
- This is a sound security default, but the API response does not tell native
  clients that their current tokens are invalid.

Implementation:

- [x] Keep all-device revocation as the default.
- [x] Return a typed `reauthentication_required: true` field after operations
  that revoke the caller.
- [x] Document that iOS clients must remove the refresh token from Keychain and
  clear the in-memory access token.
- [x] Update `docs/security.md`, `docs/api-routes.md`, and OpenAPI.
- [x] Do not add “keep this device signed in” without a separate product and
  threat-model decision.

Tests:

- [x] Successful responses explicitly require reauthentication.
- [x] The caller's access and refresh tokens are rejected afterward.
- [x] Failed operations leave the caller's session active.

### 2.5 Apply the lock order to adjacent account workflows

The password changes introduce an explicit lock convention, but existing
account workflows must not retain the inverse order.

Audit and update:

- [x] Email-change confirmation, which currently locks the pending email row
  before the user. Use discovery lookup → user lock → pending-row lock and
  revalidation.
- [x] Refresh-token rotation, which currently uses `select_for_update()` with
  a joined user. Decode `user_id`, lock the user explicitly, then lock and
  validate the auth session.
- [x] User deactivation. Keep organization locks before the user, order all
  affected organizations by primary key, then revoke dependent sessions after
  the user lock.
- [x] Membership role/removal operations. Preserve organization → membership
  ordering and use deterministic ordering if a bulk form is introduced.
- [x] Account deletion and admin deletion. Preserve organization invariants
  before user/dependent-row teardown.

Tests:

- [x] PostgreSQL concurrency tests exercise password reset versus password
  change, email confirmation versus password change, refresh rotation versus
  session revocation, and deactivation of users sharing owned organizations.
- [x] Tests use bounded waits/timeouts so a deadlock fails clearly instead of
  hanging CI.

### 2.6 Remove dead `last_login` state

JWT login never updates `User.last_login`, while `AuthSession.created_at` and
`last_used_at` already provide more useful session activity. Leaving
`last_login` visible in admin presents misleading data.

Implementation:

- [x] Set `last_login = None` on the custom user model.
- [x] Create the field-removal migration.
- [x] Remove `last_login` from admin fieldsets and readonly fields.
- [x] Verify Django admin/forms and token login do not assume the field exists.
- [x] Document `AuthSession.created_at` and `last_used_at` as the operational
  source for login/session activity.

Acceptance criteria for Phase 2:

- [x] Credential writes are serialized and atomic.
- [x] Reset tokens have one coherent lifecycle.
- [x] Session UX is an explicit client contract.
- [x] All touched account workflows follow the canonical lock hierarchy.
- [x] `last_login` no longer exposes misleading dead state.
- [x] HTTP handlers no longer contain transaction orchestration.

---

## Phase 3: Close the organization-slug existence oracle

This is a low-severity but real information disclosure and contradicts the API
convention that cross-tenant resources are treated as not found.

Current behavior in `organizations/scope.py:resolve_org_scope`:

- Unknown slug returns 404.
- Existing slug without membership returns 403.
- Any authenticated user can test whether an organization slug exists.

Recommended implementation:

- [x] For ordinary users, resolve membership and organization in one scoped
  query such as `Membership.objects.select_related("organization")` filtered
  by the user and `organization__slug`.
- [x] If no membership is found, return the same 404 status and error shape used
  for an unknown slug.
- [x] Keep a separate platform-admin branch that resolves any organization.
- [x] Preserve audit logging for platform-admin cross-tenant access.
- [x] Ensure write/admin scope helpers inherit the same non-enumerating lookup.
- [x] Review polymorphic object resolution for consistent 404 behavior after
  the canonical scope lookup succeeds.

Tests:

- [x] Unknown slug and inaccessible existing slug have identical status and
  response shape through the real API.
- [x] Query-count tests prove the ordinary-user resolver performs exactly one
  database query for an accessible organization.
- [x] Query-count tests prove unknown and inaccessible slugs each perform
  exactly one database query.
- [x] A member still resolves their organization and role.
- [x] A platform administrator still resolves and audits cross-tenant access.
- [x] Cross-tenant contact, tag, image, and export routes do not reveal whether
  the target organization exists.

Acceptance criteria:

- [x] No authenticated tenant route distinguishes nonexistent from inaccessible
  organization slugs.
- [x] The ordinary-user resolver performs exactly one query by resolving the
  membership and related organization together.

---

## Phase 4: Make pending-token handling explicit

This is cheap, high-value alignment with the style guide.

Current behavior:

- `PendingTokenMixin.save()` silently hashes a token that does not look hashed.
- Security-sensitive transformation is hidden inside a generic persistence
  hook.
- Pending token fields use `generate_hashed_token` defaults.
- A default-generated hash has no corresponding raw token and therefore creates
  an unusable pending record.

Target behavior:

- Raw tokens exist only transiently inside an account operation.
- Account operations generate a raw token and its hash together.
- Only the hash reaches a model constructor or update query.
- Saving a model never silently changes credential material.

Implementation:

- [x] Add or retain one explicit helper returning `(raw_token, token_hash)`.
- [x] Update registration, email-change, and password-reset creation paths to
  supply the hash explicitly.
- [x] Remove `generate_hashed_token` defaults from all pending-token fields.
- [x] Remove `PendingTokenMixin.save()` and unused hash-shape detection.
- [x] Create the schema migration.
- [x] Keep unique constraints on stored hashes.
- [x] Ensure admin cannot create unusable pending records accidentally; pending
  models can be read-only if manual creation has no valid use-case.

Tests:

- [x] Raw tokens are never stored.
- [x] Every supported creation path persists the expected hash.
- [x] Model creation without a token fails explicitly rather than inventing an
  unreachable token.
- [x] Existing verification/reset/email-change flows remain single-use.

### User creation and personal organizations

`UserManager.create_user()` creates the required personal organization in the
same transaction. This is cross-domain work in a manager, but it prevents an
invalid user-without-personal-org state across framework and internal callers.

Keep this as an intentional aggregate-factory exception for now. Do not move it
to a `post_save` signal. Revisit only if a single explicit account provisioning
operation can reliably cover admin, superuser, tests, imports, and every other
creation path.

---

## Phase 5: Consolidate tenant authorization and remove dead wrappers

There is a real overlapping authorization surface, not merely a naming issue.

Current behavior:

- `organizations/scope.py` is the active endpoint abstraction.
- Most helpers in `organizations/access.py` are no longer used by production
  code beyond platform-admin detection.
- Images and tags add trivial scope wrappers.
- `core/utils/auth_utils.py` and `core/utils/polymorphic.py` contain overlapping
  organization lookup helpers.
- Tests preserve APIs that production no longer needs.

Target structure:

```text
organizations/
    scope.py       # tenant resolution and currently reused access decisions
```

Do not create `policies.py` speculatively. `is_platform_admin` belongs in
`scope.py` after consolidation. Add another module only when a concrete group
of reusable policy functions no longer has a coherent existing home.

Implementation:

- [x] Implement the non-enumerating canonical scope resolver from Phase 3.
- [x] Inventory production imports with `rg` before deletion.
- [x] Keep `OrgScope` as an immutable typed request context.
- [x] Move `is_platform_admin` into `scope.py`.
- [x] Remove access helpers used only by their own tests.
- [x] Remove `get_org_scope_for_request`/`get_org_for_request` wrappers in
  images and tags.
- [x] Remove unused `get_org_or_404` and `resolve_org_for_request` variants.
- [x] Keep polymorphic model allowlisting and object-to-org verification
  explicit.
- [x] Update tests to target the canonical resolver.
- [x] Delete tests whose only purpose was preserving dead compatibility APIs.

Acceptance criteria:

- [x] There is one obvious way to resolve organization scope.
- [x] There is one obvious place for tenant policy decisions.
- [x] Platform-admin access remains audited.
- [x] Cross-tenant resources remain inaccessible and non-enumerable.
- [x] OpenAPI is unchanged.

---

## Phase 6: Strengthen typing where it provides assurance

Completed state:

- mypy runs with the Django plugin over every application package and the
  `DjangoApiStarter` project/bootstrap package.
- `check_untyped_defs = True` checks bodies globally.
- `disallow_untyped_defs = True` is enforced for account operations and profile
  serialization, image operations, organization scope, tag services,
  authentication helpers, idempotency, and polymorphic organization resolution.
- Django/Ninja route modules remain on the global incremental setting; strict
  definition checking can expand to them as their boundaries are touched.

Incremental implementation:

- [x] Add `DjangoApiStarter` to mypy's checked packages.
- [x] Enable `check_untyped_defs = True` globally.
- [x] Fix resulting errors rather than masking whole modules.
- [x] Type all new account operations and the canonical scope resolver.
- [x] Type public image/tag operations touched by later phases.
- [x] Add narrow module overrides with `disallow_untyped_defs = True` after a
  module has been cleaned.
- [x] Expand strictness app by app.
- [x] Avoid replacing useful types with broad `Any` solely to make CI pass.
- [x] Keep migrations excluded; keep tests excluded unless checking them becomes
  clearly valuable.

Suggested order:

1. `organizations.scope`
2. `accounts.operations` and account services
3. Core idempotency/upload utilities
4. Image/tag operations touched by the refactor
5. Export helpers
6. `DjangoApiStarter` bootstrap/settings modules
7. Remaining API handlers

Acceptance criteria:

- [x] Every new public operation has typed inputs and output.
- [x] Every untyped function body is checked.
- [x] The project/bootstrap package is in scope.
- [x] CI's “mypy passes” claim accurately reflects those settings.

---

## Phase 7: Add routed security and idempotency coverage

Direct function tests remain useful for operation logic. They are not proof
that the HTTP security boundary works.

Current gap:

- Several permission and idempotency tests call router functions with
  `SimpleNamespace` requests.
- Those calls bypass JWT authentication, Ninja decorators, schema parsing,
  throttling, request-body behavior, and real multipart parsing.
- The multipart fingerprint bug is specifically hidden by synthetic request
  objects.

Implementation:

- [x] Keep fast direct tests after moving logic into operations.
- [x] Add TestClient tests for every permission-sensitive route family:
  contacts, tags, images, exports, and organization scope.
- [x] Prove missing, malformed, expired, and revoked JWT behavior through the
  router.
- [x] Prove members, outsiders, admins, owners, and platform administrators see
  the intended status and error shapes.
- [x] Test idempotency headers through real JSON requests.
- [x] Test idempotent image upload through real multipart requests.
- [x] Test reused keys with changed bodies and changed file bytes.
- [x] Exercise actual throttle decorators for representative routes.
- [x] Move clearly misplaced domain tests from `DjangoApiStarter/tests` into
  their owning app when touching them.

Do not split a large test file solely because of its line count. Split only
when distinct fixtures or responsibilities make navigation materially easier.

Acceptance criteria:

- [x] Every security-critical decorator stack has routed coverage.
- [x] Direct endpoint tests are no longer the only proof of permission or
  idempotency behavior.
- [x] Test location communicates domain ownership where practical.

---

## Phase 8: Make admin deletion respect ownership workflows

The claimed personal-organization admin regression is not currently proven:

- `organizations.signals.delete_personal_org_on_user_delete` runs for both
  model and QuerySet deletion.
- It deletes the personal organization before the user row is removed.
- Deferred owner triggers should see no remaining personal organization to
  reject.

However, current coverage is SQLite-only, and an adjacent operational issue is
real: admin deletion can bypass the friendly application precheck for users who
are the last active owner of a group. The deferred PostgreSQL trigger should
protect integrity, but operators may receive a raw database failure.

Implementation and proof:

- [x] Add PostgreSQL integration coverage for `user.delete()` with a personal
  organization.
- [x] Add PostgreSQL coverage for `User.objects.filter(...).delete()`.
- [x] Exercise `UserAdmin.delete_model` and `delete_queryset` behavior.
- [x] Prove personal organizations and avatar files follow their intended
  lifecycle.
- [x] Prove deletion of a last active group owner fails without corrupting
  data.
- [x] Disable bulk user deletion unless its multi-user ownership semantics are
  deliberately implemented.
- [x] Route supported single-user admin deletion through
  `delete_user_account` or an equivalent operation so the operator receives a
  controlled explanation.
- [x] Do not weaken the database trigger; it remains the final invariant.

Acceptance criteria:

- [x] Personal-owner deletion succeeds on PostgreSQL through supported paths.
- [x] Last-group-owner deletion fails cleanly before a raw constraint error.
- [x] Admin actions cannot bypass ownership invariants.

---

## Phase 9: Opportunistic structure improvements

These changes are worthwhile only when nearby behavior is already being
modified. They should not delay the demonstrated fixes above.

### 9.1 One account operations module

`accounts/api.py` is large because it owns multiple transaction workflows. The
correctness fixes in Phases 2 and 4 create a natural extraction point.

Phase 2 creates `accounts/operations.py` for credential mutations. This phase
formalizes what belongs there and opportunistically moves the remaining
transactional account workflows; it does not introduce a second abstraction.

Use a modest structure:

```text
accounts/
    api.py
    operations.py
    services.py
```

- `api.py`: routes, throttles, request parsing, HTTP response/error mapping.
- `operations.py`: registration, password, and email-change transactional
  workflows.
- `services.py`: lower-level token/session/email helpers.

Checklist:

- [x] Move only coherent transactional use-cases.
- [x] Do not pass a Django request into operations.
- [x] Keep response serialization at the API boundary.
- [x] Keep operations as typed functions, not a service class.
- [x] Split `operations.py` further only if it later contains independently
  evolving domains that are difficult to navigate.

### 9.2 Image and tag operations

Image relation/ordering handlers and tag unassignment endpoints contain real
mutation algorithms and some duplication.

While modifying those behaviors:

- [x] Extract repeated attach/order/cover logic into typed functions.
- [x] Put complete lock/transaction boundaries around the operation.
- [x] Move tag delete/unassignment logic beside create/rename/assign behavior.
- [x] Keep query construction separate only when it is reused or costly enough
  to deserve a name.
- [x] Do not create empty `queries.py` modules to satisfy a template.

### 9.3 Export archive extraction

`organizations/export_tasks.py` is large but coherent. The clearest independent
responsibility is portable-data serialization and ZIP construction.

Preferred first step:

```text
organizations/
    export_archive.py
    export_tasks.py
    api_export.py
```

- [x] Move serialization and archive construction into `export_archive.py`.
- [x] Keep Celery entry points, locking, recovery, retention, and state helpers
  together initially.
- [x] Keep `export_operations.py` absent because API and worker lifecycle logic
  has not developed meaningful shared complexity.
- [x] Preserve deterministic keys, heartbeats, stale recovery, late ack, and
  worker-loss behavior.

### 9.4 Dead code and compatibility cleanup

Backward compatibility is not required for this starter.

Verify and remove:

- [x] `tags/views.py` placeholder.
- [x] `tags.api.get_tags_router` and redundant router aliases.
- [x] Dynamic compatibility re-exports in `images/api/__init__.py` that are no
  longer needed after tests use canonical modules/routes.
- [x] Trivial image/tag scope wrappers removed by Phase 5.
- [x] Dead authorization helpers and their preservation-only tests.
- [x] Redundant `core.utils` barrel exports.
- [x] Generic `core/utils/utils.py`; move surviving helpers to descriptive
  modules such as `identifiers.py` or `filenames.py`.
- [x] Confirm no duplicate utility tests remain after moving imports to the
  descriptive modules.

Acceptance criteria for Phase 9:

- [x] Each moved function has a clearer responsibility and test boundary.
- [x] No module split exists solely to reduce line count.
- [x] Production imports and OpenAPI remain stable.

---

## Deferred decisions

These are valid concerns but should not be implemented speculatively.

### Transactional email outbox

An outbox closes the database-commit/task-publish gap, but it adds a model,
dispatcher, claiming protocol, stale recovery, retries, retention, and
operational monitoring. SMTP delivery still remains at-least-once.

Current security-email workflows are user-retryable:

- Registration verification can be resent.
- Password reset can be requested again.
- Email change can be restarted.

Revisit an outbox when at least one of these is true:

- Losing a scheduled message creates irreversible state.
- Payments or legally significant notifications are introduced.
- Compliance requires durable delivery attempts.
- Broker/process failures measurably cause support incidents.
- Multiple independent consumers need a durable domain event.

If adopted, keep it narrow. Do not build a general event bus without multiple
concrete use-cases.

### Persistent image upload state machine

Revisit `pending`/`ready`/`failed` image state when uploads become asynchronous,
resumable, very large, or operational orphan rates justify durable recovery.
Until then, bounded reads, compensation, traceable keys, and reconciliation are
the proportionate solution.

### Fine-grained staff Django admin

The API considers only superusers platform administrators. The safest current
admin default is to reserve tenant/PII administration for platform operators.

If organization-scoped support staff becomes a requirement, scope all of:

- Changelist querysets
- Direct object URLs
- Add/change/delete permissions
- Bulk actions
- Autocomplete endpoints
- Foreign-key widgets
- History views

Partial scoping is worse than an explicit superuser-only policy because it
creates a false sense of isolation.

### Notification preference schema

`notification_preferences` is currently returned but not writable through the
profile update schema. Before exposing writes, define known keys, defaults,
unknown-key behavior, nested limits, and a serialized-size bound.

### Password validation in the manager

Do not add interactive password validation to `UserManager.create_user` by
default. It is a low-level Django factory used by controlled internal code and
tests. Public account provisioning must run validators in the account
operation or form boundary.

---

## Explicit non-goals

Do not introduce these without a separate concrete requirement:

- A repository layer that only wraps the Django ORM
- Stateful service classes used as namespaces
- Full CQRS or separate read/write persistence models
- A general event bus
- Dependency injection for every model, setting, logger, or Django primitive
- Value objects for every identifier or request schema
- Correctness-critical workflows hidden in signals
- A wholesale directory rewrite
- Elixir-shaped architecture that fights Django conventions
- File or test splitting performed only to reduce line count

---

## Suggested commit sequence

1. `fix: bound image upload resources`
2. `fix: fingerprint multipart idempotency content`
3. `fix: serialize credential mutations`
4. `fix: hide inaccessible organization slugs`
5. `refactor: make pending token handling explicit`
6. `refactor: consolidate tenant scope`
7. `chore: remove dead compatibility helpers`
8. `chore: strengthen mypy coverage`
9. `test: exercise routed security boundaries`
10. `fix: make admin account deletion ownership-aware`
11. `refactor: formalize the account operations boundary`
12. `refactor: isolate export archive construction`

The last two are opportunistic and can be combined with the behavioral slice
that motivates them. Every commit should leave the full suite green.

## Final validation checklist

- [x] Full pytest suite passes.
- [x] PostgreSQL integration tests for constraints, row locks, triggers, and
  concurrency pass.
- [x] Routed tests cover authentication, tenant isolation, throttling,
  idempotency, and multipart parsing.
- [x] mypy passes with `DjangoApiStarter` included and
  `check_untyped_defs = True`.
- [x] Black, isort, the CI Flake8 fatal-error selection, and
  `git diff --check` pass.
- [x] `manage.py check` passes under test and production settings.
- [x] `makemigrations --check --dry-run` reports no missing migrations.
- [x] Production Compose renders successfully with representative environment
  variables.
- [x] OpenAPI is regenerated and reviewed for intentional changes only.
- [x] Image storage failure and DB rollback scenarios have focused tests.
- [x] Credential concurrency and token single-use behavior have PostgreSQL
  tests.
- [x] Multi-row account and organization workflows follow the documented
  organization → user → dependent-row lock hierarchy.
- [x] Unknown and inaccessible organization slugs have identical routed
  responses.
- [x] The ordinary-user organization resolver uses exactly one query for
  accessible, inaccessible, and unknown slugs.
- [x] `last_login` is removed from the model, database schema, and admin.
- [x] Admin direct and bulk deletion behavior is explicitly tested.
- [x] Environment, security, and operations documentation reflects new limits
  and client reauthentication behavior.
- [x] This checklist records any deliberately deferred or rejected item.
