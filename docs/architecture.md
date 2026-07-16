# Architecture

The code is a modular Django monolith. HTTP concerns live in each app's
`api.py`/`schemas.py`; writes spanning models or side effects live in
`services.py`; asynchronous entry points live in task modules. Authorization is
centralized in `organizations`, while `core` owns shared transport, storage,
image, logging, health, and email boundaries.

```text
HTTP / Celery
    -> API schemas and task entry points
    -> organization scope and role policy
    -> domain services
    -> Django models / PostgreSQL
    -> Redis, SMTP, or S3-compatible storage at explicit boundaries
```

## App responsibilities

- `accounts`: user identity, registration/reset/email-change state, password
  policy, auth sessions, JWT issue/rotation/revocation.
- `organizations`: tenant and membership roles, scope resolution, personal-org
  lifecycle, portability export jobs.
- `contacts`: organization-scoped contact CRUD and public contact avatars.
- `tags`: organization-scoped tags and allowlisted generic tag relations.
- `images`: private media library, allowlisted relations, signed URLs and shares.
- `core`: cross-cutting primitives only; it must not own domain policy.

Database state is authoritative. Redis is disposable cache/broker state. Private
objects and public avatars use separate buckets/namespaces. External writes are
ordered around database transactions and compensated when later steps fail.
Idempotency records are durable PostgreSQL state: protected database mutations
and their replay responses commit together under transaction-scoped locks.

Signals are limited to local cache invalidation and narrowly defined lifecycle
safety. Critical onboarding and deletion flows use explicit transactional
services so callers can see and test the behavior.

Membership role changes and removals also go through `organizations.services`.
Groups allow multiple owners for operational resilience, while service checks
and PostgreSQL deferred triggers prevent the last active owner from being
demoted, removed, deleted, or deactivated. Group creation uses
`create_group_organization` so the organization and initial owner commit
atomically.

User, organization, and contact slugs are stable routing identifiers generated
once at creation. Editable usernames and display names never rewrite routes.
Each creator has exactly one personal organization, and its creator-owner
membership is repaired by the lifecycle service and protected in PostgreSQL.

## Extension rules

New tenant resources must carry an organization foreign key, use the common
scope resolver before lookup, include database constraints/indexes, and add
cross-tenant integration tests. Add a model to polymorphic tags/images only in
the explicit allowlist after proving its organization relationship.
