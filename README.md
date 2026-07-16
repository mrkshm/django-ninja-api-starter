# Django Ninja API Starter

Internal starting point for new organization-scoped APIs. It provides a
hardened baseline and documented operating assumptions; it does not make a new
product production-ready by itself. Review the product's authorization,
privacy, availability, abuse, and compliance requirements before launch.

The template includes:

- Django Ninja on PostgreSQL, with Redis for caching and Celery
- first-party email/password authentication and revocable rotating JWT sessions
- organization roles, tenant-scoped contacts, tags, and private images
- public user/contact avatars and private S3-compatible media
- durable idempotency for bulk image mutations and asynchronous organization
  exports
- a single-host production Compose example with Caddy

This is a fresh-start template. We do not preserve compatibility with earlier
versions of the starter when beginning a new application.

## Local setup

Requirements: Python 3.14, [uv](https://docs.astral.sh/uv/), Docker, and Docker
Compose.

```sh
cp env.example .env
docker compose up -d db redis
uv sync --frozen
uv run python manage.py migrate
uv run python manage.py seed_demo --password local-demo-password
uv run python manage.py runserver
```

Useful endpoints:

- API: `http://localhost:8000/api/v1/`
- OpenAPI UI: `http://localhost:8000/api/v1/docs`
- health: `http://localhost:8000/health/live/` and `/health/ready/`

Run Celery when working on email, exports, or scheduled cleanup:

```sh
uv run celery -A DjangoApiStarter worker -l INFO --queues=celery,email,exports,maintenance
uv run celery -A DjangoApiStarter beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Development email is written to the console. Uploads still use the configured
S3-compatible storage, so replace the placeholder R2/S3 values before testing
media workflows. Tests use isolated local storage.

## Checks

Run the same core checks before committing:

```sh
uv run pytest -q
uv run black --check .
uv run isort --profile black --check-only .
uv run flake8 --select=E9,F63,F7,F82 .
uv run mypy .
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check --database default
uv run pip-audit
```

The committed [OpenAPI contract](docs/openapi.json) is checked in CI. Regenerate
it intentionally after an API change:

```sh
DJANGO_SETTINGS_MODULE=DjangoApiStarter.settings.test uv run python scripts/export_openapi.py > docs/openapi.json
```

## Defaults to understand

- The JSON refresh-token flow is intended primarily for native clients. Before
  shipping a browser client, add the cookie and CSRF design described in
  [security.md](docs/security.md).
- Organization `member` is an editor role, not a read-only role. Admins and
  owners additionally control organization-level operations such as exports.
- Django superusers are cross-tenant platform administrators. Their tenant
  access is audited; ordinary staff receives no tenant bypass.
- Images and exports are private. User and contact avatars are deliberately
  public and may remain in intermediary caches after deletion.
- PostgreSQL is part of the application contract. PostGIS is optional and is
  not installed by default.
- Redis is disposable cache/broker state. PostgreSQL remains authoritative for
  sessions, idempotency, jobs, and domain data.

These defaults are starting decisions, not universal product requirements.
Change them consistently in policy, schema, tests, documentation, and client
behavior when a product needs different semantics.

## Deployment

[compose.production.yaml](compose.production.yaml) is the maintained deployment
example: one Linux host running Caddy, web, worker, beat, PostgreSQL, and Redis.
It is suitable only when single-host failure is acceptable and backups,
monitoring, patching, restores, and incident response have a named owner. It is
not a high-availability topology.

Follow [deployment.md](docs/deployment.md) and
[operations.md](docs/operations.md); do not deploy from the local development
Compose file or treat passing tests as a substitute for release review.

## Documentation

- [Architecture and extension rules](docs/architecture.md)
- [API routes and conventions](docs/api-routes.md)
- [Authentication and security](docs/security.md)
- [Environment variables](docs/environment.md)
- [Production deployment](docs/deployment.md)
- [Operations, backups, and incidents](docs/operations.md)
- [Optional PostGIS](docs/postgis.md)
- [Upgrade procedure](docs/upgrades.md)
- [Hardening checklist](docs/hardening/production-readiness-checklist.md)
