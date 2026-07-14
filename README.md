# Django Ninja API Starter

A production-oriented Django Ninja starter for an organization-scoped API. It
includes first-party email/password authentication, revocable rotating JWT
sessions, PostgreSQL, Redis/Celery, private S3-compatible media, public avatars,
and an asynchronous portability export.

This repository is a fresh-start template. Its API and initial migrations are
not intended to upgrade older versions of the project.

## Quickstart

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

The API is at `http://localhost:8000/api/v1/`, interactive documentation at
`http://localhost:8000/api/docs`, liveness at `/health/live/`, and readiness at
`/health/ready/`.

Run the worker and scheduler in separate terminals when exercising email,
exports, or cleanup:

```sh
uv run celery -A DjangoApiStarter worker -l INFO --queues=celery,email,exports,maintenance
uv run celery -A DjangoApiStarter beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Development uses the console email backend. Configure the S3-compatible values
in `.env` before testing uploads; tests use isolated local storage.

## Verification commands

```sh
uv run pytest -q
uv run black --check .
uv run flake8 --select=E9,F63,F7,F82 .
uv run mypy .
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run pip-audit
```

The committed [OpenAPI contract](docs/openapi.json) is generated with:

```sh
DJANGO_SETTINGS_MODULE=DjangoApiStarter.settings.test uv run python scripts/export_openapi.py > docs/openapi.json
```

## Security model

- Access tokens live for five minutes. Refresh tokens live for 30 days, rotate
  on use, and belong to a revocable device session.
- iOS clients store refresh tokens in Keychain. JSON refresh tokens are not a
  safe browser persistence mechanism; see [security.md](docs/security.md).
- Every ordinary domain resource is scoped below
  `/api/v1/orgs/{org_slug}/...`. Members can manage ordinary content; admin and
  owner roles protect exports and organization-level management.
- General images are private and delivered with short-lived signed URLs.
  Explicit share tokens are hashed, expiring, revocable, and resolved by POST.
- User and contact avatars are intentionally public. They use random keys in a
  dedicated public bucket/namespace and do not expose private media.

## Documentation

- [Architecture](docs/architecture.md)
- [API routes and conventions](docs/api-routes.md)
- [Authentication and security](docs/security.md)
- [Production deployment](docs/deployment.md)
- [Operations, backups, and incidents](docs/operations.md)
- [Environment variables](docs/environment.md)
- [Optional PostGIS](docs/postgis.md)
- [Dependency and framework upgrades](docs/upgrades.md)
- [Hardening checklist](docs/hardening/production-readiness-checklist.md)

Production deployment uses the included single-server Docker Compose topology
with Caddy. Kamal is intentionally unsupported.
