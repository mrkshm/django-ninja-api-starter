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

## Working rules

- Preserve public API behavior unless a checklist item explicitly changes it.
- Make one independently reviewable commit per coherent slice.
- Move tested behavior instead of recreating it from memory.
- Prefer explicit functions and Django ORM operations over service classes or
  repository wrappers.
- Keep database transactions short and external storage/network calls visible.
- Add concurrency tests against PostgreSQL where correctness depends on locks,
  constraints, deferred triggers, or advisory locks.
- Regenerate and review OpenAPI after every intentional contract change.
- Update this checklist when a decision changes.

## Priority summary

### Do first: demonstrated bugs and risks

- [ ] Bound every image upload read.
- [ ] Cap bulk image file count and aggregate input size.
- [ ] Fingerprint multipart idempotency requests using file content.
- [ ] Make password changes atomic with session revocation.
- [ ] Make password-reset tokens concurrency-safe and single-use.
- [ ] Enforce one coherent pending password-reset state per user.
- [ ] Make inaccessible and nonexistent organization slugs indistinguishable.
- [ ] Remove hidden pending-token hashing and unusable token defaults.

### Do next: simplify real duplication and strengthen assurance

- [ ] Consolidate tenant scope and authorization helpers.
- [ ] Remove dead wrappers and compatibility exports.
- [ ] Include the project package in mypy and enable checking untyped bodies.
- [ ] Add routed permission, multipart, and idempotency tests.
- [ ] Move account transactions into one explicit operations module while
  implementing the credential fixes.
- [ ] Add PostgreSQL and admin coverage for user-deletion ownership behavior.

### Do only if the code benefits while being changed

- [ ] Move repeated image/tag mutation algorithms out of HTTP handlers.
- [ ] Extract export archive construction from the Celery task module.
- [ ] Reorganize test locations where ownership is currently misleading.

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

- [ ] Define one authoritative accessor for `UPLOAD_IMAGE_MAX_BYTES`.
- [ ] Reuse `read_uploaded_file_bounded` for the image library.
- [ ] Prefer passing bounded bytes into `upload_image_file` so the operation's
  memory contract is explicit.
- [ ] Preserve MIME-prefix checks as an early rejection only; Pillow content
  validation remains authoritative.
- [ ] Return a stable 400 response for declared and streamed oversize failures.
- [ ] Ensure an upload whose declared size exceeds the limit is never read.
- [ ] Keep normalized/variant generation after the bounded read.

Tests:

- [ ] A declared oversized image is rejected without calling `read()`.
- [ ] An unknown-size oversized stream reads at most `max_bytes + 1`.
- [ ] A dishonest declared size cannot bypass the bound.
- [ ] Valid images still generate all expected variants.
- [ ] Invalid content and decompression-bomb failures remain controlled 400s.

### 1.2 Cap bulk upload work

Current behavior:

- `images/api/uploads.py:bulk_upload_images` materializes and processes every
  submitted file.
- There is no explicit application-level count or aggregate-size limit.

Implementation:

- [ ] Add `UPLOAD_IMAGE_MAX_FILES_PER_REQUEST`.
- [ ] Add `UPLOAD_IMAGE_MAX_TOTAL_BYTES`.
- [ ] Choose conservative starter defaults, for example 20 files and 50 MiB
  aggregate input, while retaining the per-file limit.
- [ ] Reject excessive file count before processing any image.
- [ ] Reject excessive declared aggregate size before processing.
- [ ] Track bytes actually read so unknown or dishonest sizes cannot bypass the
  aggregate limit.
- [ ] Document settings in `docs/environment.md` and the example environment.

Tests:

- [ ] File count above the limit is rejected.
- [ ] Declared aggregate size above the limit is rejected.
- [ ] Actual aggregate bytes above the limit are rejected.
- [ ] Exact boundary values are accepted.
- [ ] Rejection performs no storage writes or image-row creation.

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

- [ ] Extend `run_idempotently` to accept an explicit request fingerprint or a
  bounded fingerprint callback.
- [ ] Prepare bounded file content once, before the idempotent operation.
- [ ] Hash field name, stable file order, normalized non-file values, file
  metadata, and file bytes.
- [ ] Pass the digest to the idempotency layer without rereading the request
  stream.
- [ ] Keep generic JSON fingerprint normalization for JSON endpoints.
- [ ] Do not silently replace an unreadable body with an empty body when doing
  so weakens identity; use the explicit multipart path or return a controlled
  error.

Required semantics:

- [ ] Same key and identical content replays the stored response.
- [ ] Same key with different bytes returns 409 even when metadata matches.
- [ ] Same content under a different key executes independently.
- [ ] File ordering semantics are explicit and tested.
- [ ] Fingerprinting never performs an unbounded read.

### 1.4 Keep cross-system cleanup proportionate

The database idempotency transaction cannot make S3 writes atomic. A database
failure after storage succeeds can leave unreferenced objects.

The risk is real, but a full persistent upload state machine is not justified
for the current synchronous starter.

Implement now:

- [ ] Use storage keys that are traceable to an image/operation identifier.
- [ ] Keep best-effort cleanup for known partial failures.
- [ ] Add a focused test for a DB failure after storage writes.
- [ ] Ensure the existing media audit reports unreferenced image keys.
- [ ] Verify age-gated cleanup can safely remove those keys.
- [ ] Document that Postgres and object storage are not one atomic system.

Do **not** add `pending`/`ready` upload state solely for theoretical atomicity.
Revisit a durable upload lifecycle if uploads become asynchronous, resumable,
or operational evidence shows meaningful orphan accumulation.

Acceptance criteria for Phase 1:

- [ ] No image path performs an unbounded request-file read.
- [ ] Bulk work has count and byte budgets.
- [ ] Multipart retries distinguish actual content.
- [ ] Known failures compensate; unknown orphans are reconcilable.
- [ ] Routed multipart tests cover the real Ninja/Django stack.

---

## Phase 2: Make credential mutations atomic

Credential operations should own their complete transaction, including token
consumption and session invalidation.

### 2.1 Atomic password change

Current behavior:

- `accounts/api.py:change_password` verifies and saves the password, then calls
  `revoke_all_sessions` separately.
- A failure between those operations can leave old sessions active after the
  password changes.

Implementation:

- [ ] Add `change_password` to `accounts/operations.py`.
- [ ] Lock the user row with `select_for_update()`.
- [ ] Verify the current password against the locked row.
- [ ] Validate the new password.
- [ ] Save the password, revoke sessions, and increment `auth_version` in one
  transaction.
- [ ] Emit the audit event only after the operation succeeds.
- [ ] Keep request parsing and HTTP error/response mapping in `accounts/api.py`.

Tests:

- [ ] Password update and session invalidation succeed together.
- [ ] Simulated session-revocation failure rolls back the password.
- [ ] Incorrect current password changes nothing.
- [ ] Existing access and refresh tokens fail after success.

### 2.2 Atomic single-use password reset

Current behavior:

- `accounts/api.py:confirm_password_reset` reads the reset token without a row
  lock.
- Password update, session revocation, and token deletion are not one atomic
  transition.
- Concurrent requests can both pass validation and race to set different
  passwords.

Implementation:

- [ ] Add `confirm_password_reset` to `accounts/operations.py`.
- [ ] Hash the supplied token before lookup.
- [ ] Open one transaction and lock the pending reset row.
- [ ] Lock the associated user row.
- [ ] Recheck expiry while holding the lock.
- [ ] Validate and save the password.
- [ ] Revoke all sessions and increment `auth_version`.
- [ ] Delete the pending reset in the same transaction.
- [ ] Return a small result or raise a domain error; map it to the stable API
  response at the boundary.

Tests:

- [ ] A reset token succeeds once.
- [ ] Reuse returns the generic invalid/expired response.
- [ ] A PostgreSQL concurrency test proves only one simultaneous confirmation
  succeeds.
- [ ] A failure during credential/session mutation leaves a consistent password
  and token state.

### 2.3 One pending reset per user

Current behavior:

- Reset request deletes existing rows and then creates a replacement without
  one transaction.
- `PendingPasswordReset` permits multiple rows per user under concurrency.

Recommended default:

- [ ] Enforce one pending reset per user with a one-to-one relation or unique
  constraint.
- [ ] Rotate the pending token with `update_or_create` in a transaction.
- [ ] Treat concurrent reset requests as replacement of the same pending
  operation.
- [ ] Preserve the enumeration-resistant generic response.
- [ ] Ensure an old rotated link is invalid.

### 2.4 Make forced reauthentication explicit

Current behavior:

- Password change and completed email change revoke every device session,
  including the initiating session.
- This is a sound security default, but the API response does not tell native
  clients that their current tokens are invalid.

Implementation:

- [ ] Keep all-device revocation as the default.
- [ ] Return a typed `reauthentication_required: true` field after operations
  that revoke the caller.
- [ ] Document that iOS clients must remove the refresh token from Keychain and
  clear the in-memory access token.
- [ ] Update `docs/security.md`, `docs/api-routes.md`, and OpenAPI.
- [ ] Do not add “keep this device signed in” without a separate product and
  threat-model decision.

Tests:

- [ ] Successful responses explicitly require reauthentication.
- [ ] The caller's access and refresh tokens are rejected afterward.
- [ ] Failed operations leave the caller's session active.

Acceptance criteria for Phase 2:

- [ ] Credential writes are serialized and atomic.
- [ ] Reset tokens have one coherent lifecycle.
- [ ] Session UX is an explicit client contract.
- [ ] HTTP handlers no longer contain transaction orchestration.

---

## Phase 3: Close the organization-slug existence oracle

This is a low-severity but real information disclosure and contradicts the API
convention that cross-tenant resources are treated as not found.

Current behavior in `organizations/scope.py:resolve_org_scope`:

- Unknown slug returns 404.
- Existing slug without membership returns 403.
- Any authenticated user can test whether an organization slug exists.

Recommended implementation:

- [ ] For ordinary users, resolve membership and organization in one scoped
  query such as `Membership.objects.select_related("organization")` filtered
  by the user and `organization__slug`.
- [ ] If no membership is found, return the same 404 status and error shape used
  for an unknown slug.
- [ ] Keep a separate platform-admin branch that resolves any organization.
- [ ] Preserve audit logging for platform-admin cross-tenant access.
- [ ] Ensure write/admin scope helpers inherit the same non-enumerating lookup.
- [ ] Review polymorphic object resolution for consistent 404 behavior after
  the canonical scope lookup succeeds.

Tests:

- [ ] Unknown slug and inaccessible existing slug have identical status and
  response shape through the real API.
- [ ] A member still resolves their organization and role.
- [ ] A platform administrator still resolves and audits cross-tenant access.
- [ ] Cross-tenant contact, tag, image, and export routes do not reveal whether
  the target organization exists.

Acceptance criteria:

- [ ] No authenticated tenant route distinguishes nonexistent from inaccessible
  organization slugs.
- [ ] The ordinary-member path does not add a query and ideally uses one fewer
  query than the current implementation.

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

- [ ] Add or retain one explicit helper returning `(raw_token, token_hash)`.
- [ ] Update registration, email-change, and password-reset creation paths to
  supply the hash explicitly.
- [ ] Remove `generate_hashed_token` defaults from all pending-token fields.
- [ ] Remove `PendingTokenMixin.save()` and unused hash-shape detection.
- [ ] Create the schema migration.
- [ ] Keep unique constraints on stored hashes.
- [ ] Ensure admin cannot create unusable pending records accidentally; pending
  models can be read-only if manual creation has no valid use-case.

Tests:

- [ ] Raw tokens are never stored.
- [ ] Every supported creation path persists the expected hash.
- [ ] Model creation without a token fails explicitly rather than inventing an
  unreachable token.
- [ ] Existing verification/reset/email-change flows remain single-use.

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
    scope.py       # authenticated tenant resolution
    policies.py    # reusable context-dependent decisions, if needed
```

Implementation:

- [ ] Implement the non-enumerating canonical scope resolver from Phase 3.
- [ ] Inventory production imports with `rg` before deletion.
- [ ] Keep `OrgScope` as an immutable typed request context.
- [ ] Move `is_platform_admin` and any genuinely reused policy functions to the
  canonical module.
- [ ] Remove access helpers used only by their own tests.
- [ ] Remove `get_org_scope_for_request`/`get_org_for_request` wrappers in
  images and tags.
- [ ] Remove unused `get_org_or_404` and `resolve_org_for_request` variants.
- [ ] Keep polymorphic model allowlisting and object-to-org verification
  explicit.
- [ ] Update tests to target the canonical resolver and policies.
- [ ] Delete tests whose only purpose was preserving dead compatibility APIs.

Acceptance criteria:

- [ ] There is one obvious way to resolve organization scope.
- [ ] There is one obvious place for tenant policy decisions.
- [ ] Platform-admin access remains audited.
- [ ] Cross-tenant resources remain inaccessible and non-enumerable.
- [ ] OpenAPI is unchanged.

---

## Phase 6: Strengthen typing where it provides assurance

Current behavior:

- mypy runs with the Django plugin over the six application packages.
- `DjangoApiStarter` is excluded from the explicit package list, leaving API,
  settings, middleware, Celery, ASGI, and WSGI bootstrap code outside the main
  target.
- `check_untyped_defs = False` means unannotated function bodies are skipped.
- `disallow_untyped_defs = False` permits public operations without types.

This is meaningful but limited checking—not no checking at all.

Incremental implementation:

- [ ] Add `DjangoApiStarter` to mypy's checked packages.
- [ ] Enable `check_untyped_defs = True` globally.
- [ ] Fix resulting errors rather than masking whole modules.
- [ ] Type all new account operations and the canonical scope resolver.
- [ ] Type public image/tag operations touched by later phases.
- [ ] Add narrow module overrides with `disallow_untyped_defs = True` after a
  module has been cleaned.
- [ ] Expand strictness app by app.
- [ ] Avoid replacing useful types with broad `Any` solely to make CI pass.
- [ ] Keep migrations excluded; keep tests excluded unless checking them becomes
  clearly valuable.

Suggested order:

1. `organizations.scope` and policies
2. `accounts.operations` and account services
3. Core idempotency/upload utilities
4. Image/tag operations touched by the refactor
5. Export helpers
6. `DjangoApiStarter` bootstrap/settings modules
7. Remaining API handlers

Acceptance criteria:

- [ ] Every new public operation has typed inputs and output.
- [ ] Every untyped function body is checked.
- [ ] The project/bootstrap package is in scope.
- [ ] CI's “mypy passes” claim accurately reflects those settings.

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

- [ ] Keep fast direct tests after moving logic into operations.
- [ ] Add TestClient tests for every permission-sensitive route family:
  contacts, tags, images, exports, and organization scope.
- [ ] Prove missing, malformed, expired, and revoked JWT behavior through the
  router.
- [ ] Prove members, outsiders, admins, owners, and platform administrators see
  the intended status and error shapes.
- [ ] Test idempotency headers through real JSON requests.
- [ ] Test idempotent image upload through real multipart requests.
- [ ] Test reused keys with changed bodies and changed file bytes.
- [ ] Exercise actual throttle decorators for representative routes.
- [ ] Move clearly misplaced domain tests from `DjangoApiStarter/tests` into
  their owning app when touching them.

Do not split a large test file solely because of its line count. Split only
when distinct fixtures or responsibilities make navigation materially easier.

Acceptance criteria:

- [ ] Every security-critical decorator stack has routed coverage.
- [ ] Direct endpoint tests are no longer the only proof of permission or
  idempotency behavior.
- [ ] Test location communicates domain ownership where practical.

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

- [ ] Add PostgreSQL integration coverage for `user.delete()` with a personal
  organization.
- [ ] Add PostgreSQL coverage for `User.objects.filter(...).delete()`.
- [ ] Exercise `UserAdmin.delete_model` and `delete_queryset` behavior.
- [ ] Prove personal organizations and avatar files follow their intended
  lifecycle.
- [ ] Prove deletion of a last active group owner fails without corrupting
  data.
- [ ] Disable bulk user deletion unless its multi-user ownership semantics are
  deliberately implemented.
- [ ] Route supported single-user admin deletion through
  `delete_user_account` or an equivalent operation so the operator receives a
  controlled explanation.
- [ ] Do not weaken the database trigger; it remains the final invariant.

Acceptance criteria:

- [ ] Personal-owner deletion succeeds on PostgreSQL through supported paths.
- [ ] Last-group-owner deletion fails cleanly before a raw constraint error.
- [ ] Admin actions cannot bypass ownership invariants.

---

## Phase 9: Opportunistic structure improvements

These changes are worthwhile only when nearby behavior is already being
modified. They should not delay the demonstrated fixes above.

### 9.1 One account operations module

`accounts/api.py` is large because it owns multiple transaction workflows. The
correctness fixes in Phases 2 and 4 create a natural extraction point.

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

- [ ] Move only coherent transactional use-cases.
- [ ] Do not pass a Django request into operations.
- [ ] Keep response serialization at the API boundary.
- [ ] Keep operations as typed functions, not a service class.
- [ ] Split `operations.py` further only if it later contains independently
  evolving domains that are difficult to navigate.

### 9.2 Image and tag operations

Image relation/ordering handlers and tag unassignment endpoints contain real
mutation algorithms and some duplication.

While modifying those behaviors:

- [ ] Extract repeated attach/order/cover logic into typed functions.
- [ ] Put complete lock/transaction boundaries around the operation.
- [ ] Move tag delete/unassignment logic beside create/rename/assign behavior.
- [ ] Keep query construction separate only when it is reused or costly enough
  to deserve a name.
- [ ] Do not create empty `queries.py` modules to satisfy a template.

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

- [ ] Move serialization and archive construction into `export_archive.py`.
- [ ] Keep Celery entry points, locking, recovery, retention, and state helpers
  together initially.
- [ ] Extract `export_operations.py` only if API and worker lifecycle logic
  develops meaningful shared complexity.
- [ ] Preserve deterministic keys, heartbeats, stale recovery, late ack, and
  worker-loss behavior.

### 9.4 Dead code and compatibility cleanup

Backward compatibility is not required for this starter.

Verify and remove:

- [ ] `tags/views.py` placeholder.
- [ ] `tags.api.get_tags_router` and redundant router aliases.
- [ ] Dynamic compatibility re-exports in `images/api/__init__.py` that are no
  longer needed after tests use canonical modules/routes.
- [ ] Trivial image/tag scope wrappers removed by Phase 5.
- [ ] Dead authorization helpers and their preservation-only tests.
- [ ] Redundant `core.utils` barrel exports.
- [ ] Generic `core/utils/utils.py`; move surviving helpers to descriptive
  modules such as `identifiers.py` or `filenames.py`.
- [ ] Duplicate utility tests discovered during deletion.

Acceptance criteria for Phase 9:

- [ ] Each moved function has a clearer responsibility and test boundary.
- [ ] No module split exists solely to reduce line count.
- [ ] Production imports and OpenAPI remain stable.

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

### Profile metadata decisions

`last_login` is currently not updated by JWT login, while `AuthSession` already
records session activity. Decide later whether to remove `last_login` or update
it only on new token-pair login. Do not leave it as misleading admin data.

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
11. `refactor: extract account operations`
12. `refactor: isolate export archive construction`

The last two are opportunistic and can be combined with the behavioral slice
that motivates them. Every commit should leave the full suite green.

## Final validation checklist

- [ ] Full pytest suite passes.
- [ ] PostgreSQL integration tests for constraints, row locks, triggers, and
  concurrency pass.
- [ ] Routed tests cover authentication, tenant isolation, throttling,
  idempotency, and multipart parsing.
- [ ] mypy passes with `DjangoApiStarter` included and
  `check_untyped_defs = True`.
- [ ] Black, isort, Flake8, and `git diff --check` pass.
- [ ] `manage.py check` passes under test and production settings.
- [ ] `makemigrations --check --dry-run` reports no missing migrations.
- [ ] Production Compose renders successfully with representative environment
  variables.
- [ ] OpenAPI is regenerated and reviewed for intentional changes only.
- [ ] Image storage failure and DB rollback scenarios have focused tests.
- [ ] Credential concurrency and token single-use behavior have PostgreSQL
  tests.
- [ ] Unknown and inaccessible organization slugs have identical routed
  responses.
- [ ] Admin direct and bulk deletion behavior is explicitly tested.
- [ ] Environment, security, and operations documentation reflects new limits
  and client reauthentication behavior.
- [ ] This checklist records any deliberately deferred or rejected item.
