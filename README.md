# django-ninja-api-starter

A starter template for building REST APIs with [Django Ninja](https://django-ninja.dev) and Django.

Featuring Django, Django Ninja, Pydantic, Celery, Orjson, Pillow... all that good stuff.

## Features

- Django! Ninja! The deadly duo you don't mess with.
- JWT authentication (with Ninja Extra)
- Ready-to-use user model and authentication
- Organization-based access control
- Polymorphic tags and images
- File upload to S3-compatible storage
- GDPR-compliant data export
- Interactive API documentation
- Admin interface
- Pytest and built-in API tests
- Docker setup with PostgreSQL, Redis, and Celery
- PostGIS support
- Gunicorn configuration
- Kamal deployment


## Renaming the Project

If you want to use this starter as the base for your own project, you should rename it before starting development:

1. **Choose your new project name** (e.g., `myproject`).
2. **Search and replace** all instances of the old name (such as `DjangoApiStarter`, `django-api-starter`, or `django_ninja_api_starter`) with your new name, matching the style (PascalCase, kebab-case, snake_case) as appropriate.
   - Use your IDE's "Find and Replace in Project" feature, or run from the command line:
     ```sh
     # Replace DjangoApiStarter with MyProject everywhere (case-sensitive)
     find . -type f -exec sed -i '' 's/DjangoApiStarter/MyProject/g' {} +
     # Replace django-api-starter with myproject everywhere
     find . -type f -exec sed -i '' 's/django-api-starter/myproject/g' {} +
     ```
   - On Linux (GNU sed), use:
     ```sh
     git ls-files | xargs sed -i 's/DjangoApiStarter/MyProject/g'
     git ls-files | xargs sed -i 's/django-api-starter/myproject/g'
     ```
3. **Rename the main project directory** (`DjangoApiStarter/`) to your new name.
4. **Update references** in files like `manage.py`, `wsgi.py`, `asgi.py`, Dockerfiles, and `config/deploy.yml` if needed.
5. **Check imports and settings** for any remaining references to the old name.

## Getting Started

This project uses Docker for development and production. Follow these steps to get started:

1. Clone the repository:

```bash
git clone https://github.com/mrkshm/django-ninja-api-starter.git
cd django-ninja-api-starter
```

2. Create a `.env` file with your configuration:

```bash
# Database
POSTGRES_DB=django_db
POSTGRES_USER=django_user
POSTGRES_PASSWORD=django_pass
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Redis
REDIS_URL=redis://redis:6379/1

# Django
DJANGO_SETTINGS_MODULE=DjangoApiStarter.settings
SECRET_KEY=your-secret-key-here
DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
FRONTEND_URL=http://localhost:3000

# Server Configuration
DJANGO_ENV=development  # Set to 'production' to use Gunicorn
```

### Quickstart

```bash
# 1) Copy env and start services
cp .env.example .env
docker compose up -d --build

# 2) Apply migrations and create a superuser
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser

# 3) Open Swagger (when running locally)
open http://localhost:8000/api/docs
```

## Details

### Auth Setup using User / Organization pattern

#### Email Verification Authentication

This project implements a secure email verification system for user authentication:

- New users must verify their email address before they can log in or access protected resources.
- Verification emails are sent automatically during registration.
- Verification tokens expire after 12 hours.
- Users can request a new verification email if needed.
- Login attempts for unverified accounts return a clear message prompting verification.

#### Organization-based Access Control

This project uses an organization-based access control pattern:

- Every user is automatically assigned a personal organization when their account is created (after email verification).
- Users can also belong to additional organizations (e.g., as an employee, collaborator, or member).
- All domain entities (such as contacts, files, etc.) are associated with an organization.
- Users can access data and perform actions within their organizations.
- This pattern is suitable for many applications, ranging from apps where users may have roles in multiple groups, companies, or teams, up to true multi-tenancy where each organization acts as a fully isolated tenant.

Example use cases:

- A reader with a personal organization and as an employee of a publisher.
- Consultants working with multiple clients.

### Avatar Handling

- Avatars are uploaded to Cloudflare R2 (or any S3-compatible storage).
- Each avatar is converted and resized to two webp images:
  - **Small:** 160x160 pixels, 65% quality (filename stored in the database)
  - **Large:** 600x600 pixels, 85% quality (accessed by appending `_lg` to the small avatar filename)
- Example: If the small avatar is `avatar-johnsmith-20250421T141230-ABC123.webp`, the large version is `avatar-johnsmith-20250421T141230-ABC123_lg.webp`.

## TODO / Roadmap

- [x] Auth with User / Organization pattern
- [x] File upload to Cloudflare R2 (or other S3-compatible storage)
- [x] Contacts model
- [x] Avatar for Users and Contacts
- [x] Polymorphic tags
- [x] Polymorphic images
- [x] Docker setup with Redis
- [x] Celery for background tasks
- [x] Gunicorn production setup
- [x] GDPR-compliant data export
- [x] Admin UI
- [x] Easy deployment with Kamal
- [x] Get testing percentage to a reasonable number
- [x] Better docs

## Running Tests

To ensure tests always use local file storage (never S3 or remote), tests override the storage backend in the test code itself using the `settings` fixture:

```python
settings.STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
```

This guarantees all file operations use the local filesystem during tests.

For more details, see [`docs/testing.md`](docs/testing.md).

Run tests:

```bash
docker compose exec web pytest -q
```

## API Docs

Details about the API routes are available in the docs:

- Images & Tags API: see `docs/api-routes.md`
- Interactive OpenAPI (Swagger): available at `/api/docs` when running the server
  - Local dev: http://localhost:8000/api/docs

## Polymorphic Images and Tags

- Polymorphic Tags: assign, list, unassign, CRUD, org scoping
- Polymorphic Images: upload, attach/detach, reorder, set/unset cover, variants
- Auth, rate limits, and audit logging

## Organization Data Export (GDPR-Compliant)

Admins can export all organization data (users, contacts, tags, images, etc.) in a single ZIP archive for compliance or backup. The export is performed asynchronously via Celery, includes all images, and is delivered as a signed S3 download link via email.

- **Trigger export:** `POST /api/v1/orgs/{org_slug}/export/` (admin only)
- **Includes:** All org users, contacts (with tags), tags, and images (as files in a subfolder)
- **Delivery:** Download link sent by email, valid for 7 days
- **Security:** Only org admins can trigger and access exports

## Password Reset (Stateful, Celery-powered)

The API supports secure, stateful password resets with asynchronous email delivery via Celery.

- **Request password reset:**
  - `POST /api/v1/auth/password-reset/request`
  - Body: `{ "email": "user@example.com" }`
  - Always returns a generic success message (no info leak)
  - If the user exists, a time-limited reset token is generated and emailed
- **Confirm password reset:**
  - `POST /api/v1/auth/password-reset/confirm`
  - Body: `{ "token": "...", "new_password": "..." }`
  - Resets the password if the token is valid and not expired

**Security:**

- Tokens are single-use and expire after a short period (default: 2 hours)
- No information is leaked about whether an email exists
- All email delivery is handled asynchronously by Celery

See [docs/api-setup.md](docs/api-setup.md#password-reset-api-endpoints) for details.

## Redis Caching for Organization Permissions

This project implements Redis caching for organization membership and permission checks:

- **Cached permission checks:** Functions like `is_member`, `is_admin`, and `is_owner` use Redis to cache results for 1 hour, reducing database load and speeding up API responses.
- **Automatic cache invalidation:** When a user's organization membership changes (added or removed), Django signals clear the relevant cache keys so permission checks always reflect the latest state.

**Example:**

```python
# organizations/permissions.py
cache_key = f'is_member_{user.id}_{org.id}'
result = cache.get(cache_key)
if result is None:
    result = Membership.objects.filter(user=user, organization=org).exists()
    cache.set(cache_key, result, timeout=3600)
return result
```

See [docs/celery-and-redis.md](docs/celery-and-redis.md) for a detailed breakdown and code/test examples.

## Organization Permissions: "Loose by Default"

By default, this API uses a **loose org permission model**:

- **All members of an organization can perform all actions** (create, update, delete, view) on all resources in that organization.
- No distinction is made between admin, owner, or member for access control—membership is sufficient.

### How to Tighten Permissions

- To restrict an action to admins/owners, simply swap the `is_member` check for `is_admin` or `is_owner` in the relevant endpoint.
- You can add more granular permission logic as needed, leveraging the existing helpers.

---

For more details, see `organizations/permissions.py` and the usage in API modules like `contacts/api.py`.

## Deployment

Deployment is pre-configured for [Kamal](https://kamal-deploy.com/). To use Kamal for deployment, you must have Ruby installed on your system and Kamal installed as a Ruby gem. See the [Kamal installation guide](https://kamal-deploy.com/docs/installation/) for details.

All deployment configuration is in `config/deploy.yml` and secrets are managed in `.kamal/secrets`. For more information, see the [deployment documentation](docs/deployment.md).

## Project Structure

```
DjangoApiStarter/
├── accounts/           # User management & auth
├── organizations/      # Organization management
├── contacts/           # Contact management
├── tags/               # Tag management
├── core/               # Core utilities
├── images/             # Image management
├── DjangoApiStarter/   # Project settings
├── manage.py
└── requirements.txt
```

## Contributing

Pull requests are welcome when this is a bit more advanced.
