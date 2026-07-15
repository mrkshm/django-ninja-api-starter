# Future Refactor Improvements

This document records the next recommended refactor pass for the starter. It
is intended to be actionable after the context of the original review has
faded.

The starter is already structurally sound and does **not** need a rewrite.
These improvements address a small number of remaining correctness risks and
bring the codebase closer to the principles in
[`styleguide.md`](./styleguide.md): explicit operations, visible transaction
and side-effect boundaries, durable invariants, concurrency-safe writes, and
thin HTTP handlers.

## How to use this checklist

- Complete the phases in order unless a production issue changes the priority.
- Keep behavior and public API contracts stable unless a checklist item says
  otherwise.
- Commit each phase separately after its focused and full test suites pass.
- Prefer moving tested behavior over rewriting it from memory.
- Update this document as decisions are made or scope changes.

## Priority summary

### Correctness and durability

- [ ] Bound all image upload reads and cap bulk upload work.
- [ ] Correct multipart idempotency fingerprints.
- [ ] Make storage side effects safe when database transactions roll back.
- [ ] Make password changes and password-reset consumption atomic.
- [ ] Add durable scheduling for security-critical email.

### Structure and clarity

- [ ] Extract account lifecycle workflows from `accounts/api.py`.
- [ ] Move image and tag mutation algorithms out of HTTP handlers.
- [ ] Split export construction, lifecycle operations, and Celery entry points.
- [ ] Consolidate tenant authorization helpers.
- [ ] Remove hidden pending-token hashing from `model.save()`.

### Consistency and maintainability

- [ ] Strengthen typing incrementally.
- [ ] Reorganize large and historically misplaced tests.
- [ ] Remove dead wrappers, compatibility exports, and placeholder modules.
- [x] Review Python 3.14 multi-exception syntax and follow the configured
  formatter consistently.
- [ ] Document or replace the personal-organization deletion signal.
- [ ] Decide and document the client reauthentication contract after sensitive
  account changes.
- [ ] Restrict Django admin tenant data to platform operators or implement
  explicit staff tenant scoping.

### Hygiene completed during review

- [x] Make Django settings/environment the single source for Celery soft and
  hard time limits; remove conflicting production Compose CLI overrides.
- [x] Rebuild the migration executor on every wait poll, retry only operational
  database failures, and fail after a configurable timeout.
- [x] Validate the email-template subject convention and cache compiled
  templates.
- [x] Remove the obsolete private Ninja registry test workaround.
- [x] Confirm Black's canonical Python 3.14 multi-exception formatting.
- [x] Add bounded-query admin configuration for organizations, memberships,
  contacts, tags, and export jobs.

---

## Phase 1: Harden image uploads and multipart idempotency

This is the highest-priority phase because it contains resource-exhaustion and
cross-system consistency risks.

### 1.1 Bound every image read

Current behavior:

- `accounts` and `contacts` use `read_uploaded_file_bounded`.
- `images/services.py:upload_image_file` still calls `file.read()` without a
  limit.
- A declared upload size is useful but is not a sufficient guarantee; an
  absent, incorrect, or untrusted size must not allow an unbounded read.

Implementation:

- [ ] Change `images.services.upload_image_file` to accept already-bounded
  bytes, or make it call `read_uploaded_file_bounded` itself.
- [ ] Use `UPLOAD_IMAGE_MAX_BYTES` as the authoritative per-file limit.
- [ ] Preserve the existing MIME-prefix and Pillow content validation.
- [ ] Ensure all single and bulk upload paths use the same validator.
- [ ] Return a controlled 400 response for an oversized stream.
- [ ] Do not read an oversized declared upload at all.

Preferred shape:

```python
def prepare_image_upload(file: UploadedFile) -> PreparedImage:
    data = read_uploaded_file_bounded(file, max_bytes=image_upload_max_bytes())
    ...
```

The prepared value may be a frozen dataclass containing the normalized image,
variants, original name, and a content digest if that reduces repeated work.
Do not introduce it merely as ceremony; plain arguments are acceptable if
they remain clearer.

Tests:

- [ ] Declared oversized uploads are rejected without calling `read()`.
- [ ] Undeclared or dishonest oversized uploads are read only up to
  `max_bytes + 1` and rejected.
- [ ] Valid uploads still generate every expected variant.
- [ ] Invalid image content remains a 400 rather than a 500/503.

### 1.2 Cap bulk upload work

Current behavior:

- `images/api/uploads.py:bulk_upload_images` turns all submitted files into a
  list and processes each one.
- There is no explicit application-level file-count or aggregate-byte cap.

Implementation:

- [ ] Add settings such as `UPLOAD_IMAGE_MAX_FILES_PER_REQUEST` and
  `UPLOAD_IMAGE_MAX_TOTAL_BYTES`.
- [ ] Choose conservative starter defaults, for example 20 files and 50 MiB
  aggregate input, while retaining the existing per-file cap.
- [ ] Reject the request before image processing when the count or declared
  aggregate size exceeds the limit.
- [ ] Continue enforcing bounded reads because declared sizes are not trusted.
- [ ] Document these settings in `docs/environment.md` and the example env
  file if they are configurable through environment variables.

Tests:

- [ ] Too many files are rejected.
- [ ] Excessive aggregate size is rejected.
- [ ] The boundary values are accepted.
- [ ] A malicious unknown-size file still cannot bypass the aggregate policy.

### 1.3 Correct multipart request fingerprints

Current behavior:

- `core/utils/idempotency.py:_request_fingerprint` attempts to hash the raw
  request body.
- Bulk upload accesses `request.FILES` before calling `run_idempotently`.
- After Django parses the request stream, reading `request.body` can fail; the
  code then falls back to an empty body.
- File fingerprints contain only name, size, and content type. Two different
  files with identical metadata can therefore be treated as the same request.

Implementation options:

1. Preferred: prepare the bounded file content first and pass an explicit
   operation fingerprint to the idempotency layer.
2. Alternative: extend `run_idempotently` with a fingerprint callback that
   hashes bounded file content without rereading an unbounded request stream.

Requirements:

- [ ] Hash file bytes, not only file metadata.
- [ ] Include field name and a stable file order in the fingerprint.
- [ ] Include normalized JSON/form values where applicable.
- [ ] Do not depend on `request.body` after multipart parsing.
- [ ] Do not perform a second unbounded read.
- [ ] Reusing one key with different bytes returns 409.
- [ ] Retrying the same bounded content returns the stored response.

Tests:

- [ ] Same key, filename, size, and MIME type but different bytes returns 409.
- [ ] Same key and identical files replays the previous result.
- [ ] File ordering has explicitly tested semantics.
- [ ] Multiple form fields cannot accidentally produce the same fingerprint.

### 1.4 Separate storage effects from the database idempotency transaction

Current behavior:

- `run_idempotently` wraps the mutation and idempotency record in one database
  transaction.
- `upload_image_file` writes original and variant objects to storage inside
  that transaction.
- If the idempotency record insert or database commit fails after storage
  succeeds, image rows roll back but storage objects remain.
- Database atomicity cannot make S3 atomic.

Design goal:

Every uploaded object must be either represented by durable database state or
discoverable and safely removable by reconciliation. A database rollback must
not create permanently unknown storage keys.

Recommended design:

- [ ] Generate deterministic keys from a durable upload/image identifier,
  rather than a purely transient random token.
- [ ] Persist an upload/image state such as `pending`, `ready`, or `failed`
  before or alongside storage orchestration.
- [ ] Make storage upload resumable and idempotent for that identifier.
- [ ] Mark the image ready only after all required variants exist.
- [ ] Compensate partial uploads on known failures.
- [ ] Extend the media audit/reconciliation command to find stale pending
  uploads and deterministic orphan keys.
- [ ] Define what API clients receive while an image is pending.

For a simpler synchronous implementation, it is acceptable to keep the HTTP
request synchronous if the state machine and compensation are durable. Do not
claim that the operation is atomically committed across Postgres and S3.

Acceptance criteria:

- [ ] A forced DB failure after successful storage writes is recoverable and
  covered by a test.
- [ ] A failure after only some variants upload leaves no ready image.
- [ ] Retrying an interrupted upload does not duplicate objects or rows.
- [ ] The audit command can report and optionally clean stale upload artifacts.

---

## Phase 2: Make account credential workflows atomic

Account mutations should become explicit application operations. The API
module should authenticate the request, call the operation, translate domain
errors, and serialize the result.

### 2.1 Atomic password change

Current behavior:

- `accounts/api.py:change_password` checks and saves the password, then revokes
  sessions in separate operations.
- A failure between these steps can leave old sessions active after a password
  change.

Implementation:

- [ ] Add an operation such as
  `accounts.operations.passwords.change_password`.
- [ ] Lock the user row with `select_for_update()`.
- [ ] Verify the current password against the locked user.
- [ ] Validate and save the new password.
- [ ] Revoke all sessions and increment `auth_version` in the same database
  transaction.
- [ ] Emit the audit event only after success.
- [ ] Keep the endpoint response and error shape stable.

Tests:

- [ ] Password and session revocation succeed together.
- [ ] A simulated revocation failure rolls back the password change.
- [ ] An incorrect current password changes nothing.
- [ ] Existing access and refresh tokens are rejected after success.

### 2.2 Atomic, single-use password reset

Current behavior:

- `accounts/api.py:confirm_password_reset` fetches the token without locking.
- Password update, session revocation, and token deletion are not one atomic
  operation.
- Concurrent confirmations can race to consume the same token and set
  different passwords.

Implementation:

- [ ] Add `confirm_password_reset` to the password operations module.
- [ ] Hash the supplied token before querying.
- [ ] Use `transaction.atomic()` and lock the pending reset row.
- [ ] Lock the associated user row before changing credentials.
- [ ] Recheck expiry while holding the lock.
- [ ] Change the password, revoke sessions, bump `auth_version`, and delete the
  token in the same transaction.
- [ ] Return a domain result or raise a domain exception; keep `HttpError` at
  the API boundary where practical.

Tests:

- [ ] A reset token works once.
- [ ] A second use returns the generic invalid/expired response.
- [ ] Concurrent consumption permits only one successful transition.
- [ ] A failure during session revocation rolls back the password and preserves
  a consistent token state.

### 2.3 Normalize password-reset request state

Current behavior:

- Requesting a reset deletes existing rows and creates a new row without a
  surrounding transaction.
- `PendingPasswordReset` permits multiple rows for one user under concurrency.

Decision required:

- Either allow multiple independently valid reset links and document it, or
  enforce one active reset per user.

Recommended default:

- [ ] Enforce one pending password reset per user with a one-to-one relation or
  unique constraint.
- [ ] Rotate its token with `update_or_create` inside a transaction.
- [ ] Treat concurrent requests as replacement of the same pending operation.
- [ ] Preserve the enumeration-resistant generic response.

### 2.4 Make forced reauthentication an explicit API contract

Current behavior:

- Password change and completed email change revoke every device session,
  including the session used to initiate the operation.
- This is a reasonable security default and should remain the starter default.
- The success responses do not tell native clients that their current access
  and refresh tokens are now invalid.

Implementation:

- [ ] Return a typed response that explicitly indicates reauthentication is
  required, for example `reauthentication_required: true`.
- [ ] Document that iOS clients must clear their access token and Keychain
  refresh token after receiving a successful response.
- [ ] Ensure clients navigate to sign-in rather than discovering revocation on
  the next unrelated API request.
- [ ] Update OpenAPI, `docs/api-routes.md`, and `docs/security.md`.
- [ ] Preserve the all-device revocation stance unless a separate product
  decision introduces “keep this device” behavior.

Tests:

- [ ] Both endpoints return the explicit reauthentication signal.
- [ ] The initiating access and refresh tokens are rejected after success.
- [ ] Failed operations do not revoke the caller's session.

---

## Phase 3: Add a transactional email outbox

Security-critical email currently crosses the Postgres/Celery boundary without
durable publication. SMTP itself remains at-least-once, but scheduling the
message should survive web-process and broker failures.

### 3.1 Define the outbox model

Add a generic but deliberately small model, for example `EmailOutboxMessage`,
with:

- A UUID primary key/message ID
- Template name or explicit subject/body payload
- Recipient list
- JSON template context
- Creation and next-attempt timestamps
- `pending`, `sending`, `sent`, and `failed` status
- Attempt count and bounded error text
- Optional idempotency/deduplication key with a unique constraint

Do not build a general event bus unless another concrete use-case requires it.

Checklist:

- [ ] Define retention and cleanup for sent messages.
- [ ] Avoid logging secrets or raw verification/reset tokens.
- [ ] Decide whether token-bearing content is rendered at creation time or
  worker time. Ensure the worker has exactly the information it needs.
- [ ] Encrypt sensitive queued content if the threat model requires database
  payload encryption; otherwise document the storage decision.

### 3.2 Write pending state and outbox message atomically

Apply the outbox to:

- Registration verification
- Email-change notice to the old address
- Email-change verification at the new address
- Password reset
- Email-change completion notices where durability is desired
- Export-ready notifications if they are considered required rather than
  best-effort

Checklist:

- [ ] Create/rotate the pending token and outbox message in one transaction.
- [ ] Publish or wake the dispatcher using `transaction.on_commit()` as a
  latency optimization, not as the only durability mechanism.
- [ ] Remove API logic that deletes valid pending state merely because Celery
  publication raised.
- [ ] Return a response based on durable database acceptance.

### 3.3 Implement idempotent dispatch

- [ ] Claim rows using `select_for_update(skip_locked=True)` or an equivalent
  safe queue pattern.
- [ ] Give the email provider a stable message ID/idempotency key when the
  provider supports one.
- [ ] Narrow retries to transient transport/provider failures.
- [ ] Recover stale `sending` rows after worker loss.
- [ ] Record terminal failure without blocking unrelated messages.
- [ ] Add periodic cleanup for old sent rows.

Acceptance criteria:

- [ ] A broker outage after an API commit does not lose the email.
- [ ] Worker loss during dispatch is recoverable.
- [ ] Duplicate task delivery does not create multiple outbox rows.
- [ ] SMTP/provider ambiguity is documented as at-least-once unless the
  provider supplies idempotent delivery.

---

## Phase 4: Extract account application operations

`accounts/api.py` currently combines HTTP routing with registration,
email-change, password-reset, token creation, transactions, email scheduling,
and audit orchestration. It is the clearest structural mismatch with the style
guide.

### Proposed structure

```text
accounts/
    api.py
    token_api.py                 # optional if token routes remain substantial
    operations/
        __init__.py
        registration.py
        email_change.py
        passwords.py
        sessions.py
    models.py
    schemas.py
    tokens.py
```

Do not create a class-based service layer. Use typed functions and small result
values only where they clarify the boundary.

### Endpoint target shape

```python
@auth_router.post("/verify-registration")
def verify_registration(request, data: RegistrationVerificationSchema):
    result = registration.verify(
        token=data.token,
        password=data.password,
        device_name=data.device_name or "",
    )
    return result.to_response()
```

The exact response mapping can remain in the endpoint; operations should not
need a Django request object.

Checklist:

- [ ] Move pending registration creation and verification into
  `operations/registration.py`.
- [ ] Move email-change request and confirmation into
  `operations/email_change.py`.
- [ ] Move password change/reset behavior into `operations/passwords.py`.
- [ ] Keep token-pair/session rotation in a coherent sessions/token module.
- [ ] Pass scalar or typed values rather than the HTTP request.
- [ ] Keep throttling, request parsing, and response status selection in API
  modules.
- [ ] Keep audit events close to successful operations and ensure they cannot
  be emitted for rolled-back writes.
- [ ] Prefer domain exceptions/results internally; translate to stable API
  errors at the boundary.

Acceptance criteria:

- [ ] Account API handlers are short and describe the use-case at a glance.
- [ ] Operations can be tested without constructing HTTP requests.
- [ ] Existing API contract and enumeration-resistant responses remain stable.
- [ ] OpenAPI output changes only where intentionally documented.

---

## Phase 5: Move image and tag mutations out of API handlers

The image API is already divided by endpoint category, but relation, ordering,
cover, and bulk algorithms remain embedded in HTTP functions. Tags similarly
performs delete and unassignment mutations directly in `tags/api.py`.

### 5.1 Image operations

Suggested modules:

```text
images/
    operations.py
    queries.py
    signing.py       # optional; use only if queries.py becomes incoherent
    api/
        ...          # thin route modules
```

Move these use-cases into typed functions:

- [ ] Attach one or multiple images to an object.
- [ ] Detach one or multiple images.
- [ ] Reorder all attached images.
- [ ] Set and unset the cover image.
- [ ] Edit image metadata.
- [ ] Delete one or multiple images.
- [ ] Upload/complete an image after Phase 1 defines its durable lifecycle.

Requirements:

- [ ] Operations accept an already resolved org-scoped object or explicit
  model values, not a request.
- [ ] Transaction and locking boundaries live with the complete operation.
- [ ] Eliminate duplicated attach/order/cover logic between single and bulk
  routes.
- [ ] Preserve the database constraints as the final authority.
- [ ] Audit only actual state changes.

### 5.2 Image queries

- [ ] Move reusable listing query construction into `images/queries.py`.
- [ ] Keep presigned URL generation explicit; do not hide significant signing
  work inside an innocent-looking model property.
- [ ] Preserve tenant scoping at the API/policy boundary.

### 5.3 Tag operations and queries

Suggested modules:

```text
tags/
    operations.py
    queries.py
    api.py
```

- [ ] Move tag deletion, bulk unassignment, and unassignment-by-slug into
  operations.
- [ ] Keep tag create, rename, and assignment with those operations rather
  than a generic partial `services.py` split.
- [ ] Move ordering validation and reusable tag query construction into
  queries or typed API parameters.
- [ ] Bound tag search input length and retain pagination.
- [ ] Keep the existing assignment name normalization, deduplication, size cap,
  and atomicity.

Acceptance criteria:

- [ ] Image and tag API handlers primarily resolve scope, call an operation or
  query, and map the response.
- [ ] No mutation algorithm is duplicated across single and bulk endpoints.
- [ ] Focused operation tests cover locking and invariants without HTTP setup.

---

## Phase 6: Split organization export responsibilities

`organizations/export_tasks.py` is coherent but combines several distinct
responsibilities: export queries and serialization, ZIP construction, storage,
job state transitions, worker locking, recovery, retention, and Celery entry
points.

### Proposed structure

```text
organizations/
    export_archive.py
    export_operations.py
    export_tasks.py
    api_export.py
```

Responsibilities:

`export_archive.py`

- Query and serialize portable organization data.
- Build the ZIP archive.
- Copy source media while reporting heartbeat progress.
- Remain independent of Celery task decorators.

`export_operations.py`

- Create and queue export jobs.
- Own state transitions and conditional updates.
- Detect staleness and reset jobs for retry.
- Mark ready/failed/expired states.
- Own advisory-lock helpers if they are application-level rather than
  Celery-specific.

`export_tasks.py`

- Thin Celery entry points.
- Orchestrate archive, storage, state-transition operations, and notification.
- Recovery and cleanup task entry points.

Checklist:

- [ ] Move code without weakening the current deterministic storage key,
  heartbeat, advisory lock, stale recovery, or cleanup behavior.
- [ ] Type public archive and lifecycle functions.
- [ ] Use explicit result values for transitions when useful.
- [ ] Preserve `acks_late` and worker-loss behavior.
- [ ] Keep external storage outside long database transactions.
- [ ] Consider scheduling export notification through the email outbox.

Acceptance criteria:

- [ ] Celery task functions tell a short, coherent orchestration story.
- [ ] Archive serialization can be tested without invoking a Celery task.
- [ ] Existing crash/retry/recovery tests remain green.

---

## Phase 7: Consolidate tenant scope and authorization

Current behavior:

- `organizations/scope.py` is the active production abstraction used by most
  endpoints.
- Most helpers in `organizations/access.py` are now exercised only by their
  tests.
- Images and tags add trivial wrappers such as `get_org_scope_for_request`.
- `core/utils/auth_utils.py` and `core/utils/polymorphic.py` contain additional
  overlapping organization resolution helpers.

Because this is a fresh starter and backward compatibility is not required,
prefer one obvious access path.

### Target structure

```text
organizations/
    scope.py       # resolve authenticated tenant context
    policies.py    # context-dependent authorization decisions
```

Checklist:

- [ ] Inventory production imports before deleting helpers.
- [ ] Keep `OrgScope` as the typed, immutable request-level context.
- [ ] Keep platform-admin tenant access auditing in the canonical resolution
  path.
- [ ] Move genuine reusable policy functions into `policies.py`.
- [ ] Delete unused role/access helpers rather than preserving them for tests.
- [ ] Remove trivial wrappers in images and tags; import the canonical resolver
  directly.
- [ ] Keep polymorphic model allowlisting and cross-org verification explicit.
- [ ] Consolidate or remove `resolve_org_for_request`, `get_org_for_request`,
  and `get_org_or_404` duplicates.
- [ ] Update tests to target the canonical abstraction.

Acceptance criteria:

- [ ] There is one obvious way to resolve an organization scope.
- [ ] There is one obvious place for tenant policy decisions.
- [ ] Superuser cross-tenant access remains audited.
- [ ] Cross-tenant polymorphic access remains denied.

---

## Phase 8: Remove hidden token transformation

Current behavior:

- `PendingTokenMixin.save()` hashes any token that does not look hashed.
- This is security-sensitive behavior hidden in a generic persistence hook.
- Callers cannot tell from `save()` whether the value will be transformed.

Target behavior:

- Raw tokens exist only transiently in the operation that creates them.
- Only token hashes are ever passed to model constructors or update methods.
- Model persistence does not silently transform credentials.

Checklist:

- [ ] Add an explicit token pair/factory returning `(raw_token, token_hash)` if
  the existing helpers do not already provide the right API.
- [ ] Update registration, password reset, and email change operations to store
  only hashes.
- [ ] Remove `generate_hashed_token` model defaults. A default-generated hash
  has no corresponding raw token and creates an unusable pending record.
- [ ] Require every pending-token creation path to provide a token hash
  generated alongside the raw token.
- [ ] Remove `PendingTokenMixin.save()`.
- [ ] Add model/database validation only if it provides a real guarantee and
  does not pretend to prove cryptographic origin.
- [ ] Test that raw tokens never persist.

### User creation and personal organizations

`UserManager.create_user()` currently creates the required personal
organization inside the user creation transaction. This is cross-domain work
inside a manager, but it also makes an important aggregate invariant difficult
to bypass.

Decision:

- [ ] Document this as an intentional aggregate factory exception, **or**
- [ ] Introduce an explicit `provision_account` operation and ensure every
  framework/admin/superuser creation path uses it.

Do not move this behavior to a `post_save` signal. That would make the workflow
less explicit and weaken failure handling. Leave the manager implementation in
place unless the explicit provisioning operation can preserve the invariant
reliably.

---

## Phase 9: Review signal responsibilities

### Signals that fit the style guide

Account and contact avatar deletion signals are acceptable defense-in-depth
cleanup. The primary mutation paths already schedule old-file removal
explicitly, while signals protect deletion paths that might otherwise forget
storage cleanup.

- [ ] Keep signal registration tests.
- [ ] Keep cleanup scheduled with `transaction.on_commit()`.
- [ ] Keep deletion idempotent and safe when the object is already missing.

### Personal-organization deletion signal

`organizations/signals.py` deletes a user's personal organization during
`User` pre-delete. Correct account deletion currently depends on this signal
for deletion paths that bypass `delete_user_account`.

This is a deliberate exception or a refactor target; it should not remain
ambiguous.

Options:

1. Keep it as a documented lifecycle guard, with production-registration and
   direct/QuerySet/admin deletion tests.
2. Make direct deletion fail closed at the database level and require the
   explicit account deletion operation to remove the personal organization.
3. Redesign ownership persistence so the database can express the desired
   conditional cascade without a signal.

Recommended near-term choice:

- [ ] Keep the signal, document why it is necessary, assign a stable
  `dispatch_uid`, and test all supported deletion paths.
- [ ] Ensure `delete_user_account` remains the normal application path.
- [ ] Revisit only if the organization ownership model changes.

Do not replace this with a user `delete()` override alone; bulk/QuerySet
deletion can bypass model overrides.

---

## Phase 10: Strengthen typing incrementally

Current behavior:

- mypy runs with the Django plugin.
- The configured `files` list excludes the `DjangoApiStarter` package, leaving
  settings, middleware, API bootstrap, Celery bootstrap, ASGI, and WSGI outside
  the explicit check target.
- `check_untyped_defs` and `disallow_untyped_defs` are both disabled.
- Many API functions and application helpers therefore pass CI without their
  bodies being fully checked.

Checklist:

- [ ] Add `DjangoApiStarter` to the checked package list.
- [ ] Enable `check_untyped_defs = True` globally first.
- [ ] Type all new public operation/query functions from the preceding phases.
- [ ] Add return types to existing public services and utility boundaries.
- [ ] Use concrete model and schema types where practical.
- [ ] Add narrow module-level mypy overrides with
  `disallow_untyped_defs = True` for cleaned modules.
- [ ] Expand strictness app by app rather than weakening types with pervasive
  `Any` merely to make CI green.
- [ ] Keep migrations and tests excluded unless checking them provides enough
  value to justify the annotation cost.

Suggested progression:

1. `organizations.scope`, policies, and services
2. New account operation modules
3. Image/tag operations and queries
4. Export modules
5. Shared core utilities
6. API handlers

Acceptance criteria:

- [ ] Every new application operation has fully typed inputs and output.
- [ ] `check_untyped_defs` is enabled globally.
- [ ] No new broad `Any` types are introduced without a documented boundary.

---

## Phase 11: Reorganize tests around application ownership

Current behavior:

- `contacts/tests/test_contacts_api.py` is approximately 868 lines.
- Several domain endpoint tests live under `DjangoApiStarter/tests` rather than
  their owning application.
- Some tests import endpoint functions from compatibility exports instead of
  exercising operations or the routed API.
- Several permission and idempotency suites call router functions with
  `SimpleNamespace` request stubs. Those tests bypass Ninja authentication,
  decorators, parsing, schema validation, throttling, and real multipart
  behavior.
- Duplicate helper tests exist in places such as the core utility suites.

Checklist:

- [ ] Split the contact API suite by behavior, for example list/search,
  create/update, avatars, deletion, validation, and concurrency.
- [ ] Move account, image, tag, and permission tests from the project package
  into their owning apps.
- [ ] Prefer operation-level tests for domain logic.
- [ ] Retain API integration tests for authentication, validation, status,
  response shape, and routing.
- [ ] Add routed TestClient coverage for each permission boundary and each
  idempotent endpoint; keep direct tests only as operation-level coverage.
- [ ] Prove missing/invalid JWTs, cross-tenant users, malformed payloads,
  throttle windows, and reused idempotency keys pass through the actual Ninja
  stack.
- [ ] Avoid unit tests coupled to compatibility re-exports or private endpoint
  implementation details.
- [ ] Consolidate duplicate utility tests.
- [ ] Keep PostgreSQL-specific integration coverage for constraints, row locks,
  advisory locks, and triggers.

Acceptance criteria:

- [ ] Test location makes ownership obvious.
- [ ] No single test module becomes an unrelated grab bag.
- [ ] Moving operations out of APIs does not reduce end-to-end route coverage.

---

## Phase 12: Remove low-value compatibility and dead structure

Backward compatibility is not required for this starter. Remove aliases and
wrappers that do not serve current production code.

Candidates to verify and remove:

- [ ] `tags.views` placeholder module.
- [ ] `tags.api.get_tags_router` and redundant `tags_router` aliases; register
  `router` directly.
- [ ] Dynamic/re-export-heavy compatibility surface in `images/api/__init__.py`.
- [ ] Trivial `get_org_scope_for_request` and `get_org_for_request` wrappers.
- [ ] Unused organization access helpers retained only for their tests.
- [ ] Unused `resolve_org_for_request`/`get_org_or_404` variants.
- [ ] Redundant `core.utils` barrel exports where direct imports are clearer.
- [ ] Generic `core/utils/utils.py`; rename surviving helpers to a descriptive
  module such as `identifiers.py` or `filenames.py`.
- [ ] Duplicate tests for helpers removed during consolidation.

Also:

- [x] Review Python 3.14 bare-comma multi-exception handlers against the
  configured formatter:

```python
except TokenError, ValueError:
    ...
```

Black 26 removes the parentheses for Python 3.14 handlers that do not use
`as`, so the repository retains the formatter's canonical result rather than
adding `# fmt: skip` directives for a cosmetic preference. Handlers using
`as exc` remain parenthesized where required.

- [x] Remove the obsolete test bootstrap that manufactured and silently
  cleared the private `NinjaAPI._registry` attribute. The installed Ninja
  version no longer uses that registry for router validation.

Acceptance criteria:

- [ ] Production imports no longer rely on removed aliases.
- [ ] Tests import the canonical module or exercise the public route.
- [ ] `rg` finds no stale compatibility comments or dead references.
- [ ] OpenAPI output is unchanged.

---

## Phase 13: Resolve deferred admin and profile design decisions

The mechanical hygiene around these areas can be improved independently, but
the remaining choices affect product behavior and should be made explicitly.

### 13.1 Enforce a Django admin trust model

Completed immediate hygiene:

- [x] Replace bare registrations for organizations, memberships, contacts, and
  tags with explicit `ModelAdmin` classes.
- [x] Add useful list/search configuration and `list_select_related`.
- [x] Replace unbounded foreign-key dropdowns with `raw_id_fields`.
- [x] Make `Membership.__str__` use stored foreign-key IDs rather than causing
  implicit user and organization queries.

Deferred security decision:

The API treats only superusers as cross-tenant platform administrators. Django
admin permits any active `is_staff` user to sign in and model permissions can
then expose tenant data globally unless each admin is scoped.

Recommended starter default:

- [ ] Restrict tenant and PII model admins to superusers/platform operators.
- [ ] Add tests proving ordinary staff cannot list, search, view, change, or
  autocomplete tenant records even if model permissions are accidentally
  granted.
- [ ] If organization-scoped support staff becomes a real requirement, replace
  the blanket restriction with explicit `get_queryset`, object-permission, and
  form-field scoping based on memberships.
- [ ] Audit platform-operator changes to sensitive tenant or account data.

Do not implement partial scoping that filters changelists but leaves object
URLs, autocomplete endpoints, history, actions, or foreign-key widgets global.

### 13.2 Decide whether `last_login` is useful

Current behavior:

- JWT authentication never updates `User.last_login`.
- `AuthSession` already records session creation and refresh activity.
- The admin displays `last_login`, giving operators a misleading empty value.

Recommended choice:

- [ ] Remove the field by overriding `last_login = None`, create the migration,
  and remove it from admin fieldsets; **or**
- [ ] Update it only after a successful new token-pair login, not on refresh.
- [ ] Document which timestamp operators should use for security investigations.

The current dead/misleading state should not remain.

### 13.3 Define notification preferences before exposing them

Current behavior:

- `notification_preferences` is an unconstrained JSON object.
- It is returned by the profile schema but is not currently writable through
  `UserProfileUpdate`, so it is not an immediate untrusted-input issue.

Before making it writable:

- [ ] Define a typed schema with known keys and explicit defaults.
- [ ] Forbid unknown keys unless forward-compatible extension data is a
  deliberate requirement.
- [ ] Bound nested collections and strings.
- [ ] Cap serialized size at an appropriate boundary.
- [ ] Decide whether absent keys inherit application defaults or persist
  explicit values.
- [ ] Add a data migration if the stored representation changes.

### 13.4 Keep password validation at the public boundary

No manager change is currently recommended. `UserManager.create_user` is a
low-level Django factory used by tests and controlled internal code. Public
registration already invokes Django password validation.

- [ ] Ensure the future `provision_account`/registration operation always runs
  password validators.
- [ ] Ensure every future public/admin account-creation path uses a validated
  form or operation.
- [ ] Do not silently add password validation to the manager unless all
  low-level callers are intentionally required to obey interactive-user policy.

---

## Explicit non-goals

The refactor should **not** introduce the following without a separate,
concrete requirement:

- A repository layer that only wraps the Django ORM
- Stateful service classes used merely as namespaces
- Full CQRS with separate persistence models
- A general event bus beyond the small transactional outbox
- Dependency injection for every model, setting, logger, or Django primitive
- Value objects for every identifier or request schema
- A wholesale directory rewrite performed independently of behavior changes
- Moving correctness-critical workflows into signals
- Replacing working Django conventions solely to resemble Elixir architecture

## Suggested commit sequence

1. `fix: bound image upload resources`
2. `fix: harden multipart idempotency`
3. `fix: make image storage lifecycle recoverable`
4. `fix: serialize credential mutations`
5. `feat: add transactional email outbox`
6. `refactor: extract account operations`
7. `refactor: extract image and tag operations`
8. `refactor: split export lifecycle modules`
9. `refactor: consolidate tenant policies`
10. `refactor: make pending token hashing explicit`
11. `chore: strengthen typing and test ownership`
12. `chore: remove compatibility scaffolding`
13. `security: enforce the Django admin trust model`
14. `refactor: clarify profile and login metadata`

Each commit should be independently reviewable and leave the full suite green.

## Final completion checklist

- [ ] Full pytest suite passes.
- [ ] PostgreSQL integration tests for constraints and concurrency pass.
- [ ] mypy passes with `check_untyped_defs = True`.
- [ ] Black, isort, Flake8, and `git diff --check` pass.
- [ ] `manage.py check` passes under test and production settings.
- [ ] `makemigrations --check --dry-run` reports no missing migrations.
- [ ] OpenAPI is regenerated and reviewed for intentional changes only.
- [ ] Storage failure and DB rollback scenarios have focused tests.
- [ ] Celery worker-loss and duplicate-delivery scenarios have focused tests.
- [ ] Environment and operations documentation includes new settings, outbox
  maintenance, and media reconciliation.
- [ ] This checklist is updated to record final design decisions and any
  intentionally deferred items.
