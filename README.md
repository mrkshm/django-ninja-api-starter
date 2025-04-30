# django-ninja-api-starter

A starter template for building REST APIs with [Django Ninja](https://django-ninja.dev) and Django.

Featuring Django, Django Ninja, Pydantic, Celery, Orjson, Pillow, ImageKit... all that good stuff.

## Features

- Django! Ninja! The deadly duo you don't mess with.
- JWT authentication (with Ninja Extra)
- Ready-to-use user model and authentication
- Organization-based access control
- Polymorphic tags and images
- File upload to S3-compatible storage
- GDPR-compliant data export
- Interactive API documentation
- Pytest and built-in API tests
- Docker setup with PostgreSQL, Redis, and Celery
- PostGIS support
- Gunicorn configuration

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

3. Start the services:

```bash
# Development mode (default)
docker-compose up --build

# Production mode with Gunicorn
DJANGO_ENV=production docker-compose up --build
```

This will:

- Start PostgreSQL with PostGIS
- Start Redis
- Run database migrations
- Start the Django server (development or production mode)
- Start Celery worker and beat services

4. Create a superuser (optional):

```bash
docker-compose exec web python manage.py createsuperuser
```

Visit [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs) for interactive API documentation.

For more detailed Docker setup information, see [docs/docker-setup.md](docs/docker-setup.md).
For Gunicorn production setup, see [docs/gunicorn-setup.md](docs/gunicorn-setup.md).

## Details

### Auth Setup using User / Organization pattern

This project uses an organization-based access control pattern:

- Every user is automatically assigned a personal organization when their account is created.
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
- [ ] Easy deployment with Kamal
- [ ] Get testing percentage to a reasonable number
- [ ] Better docs
- [ ] Postman collection for API testing

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

## Polymorphic Tagging (Organization-Scoped)

You can assign tags to any model using the ContentTypes framework. Tags are scoped to the user's current organization and are unique within each organization. All tag API endpoints require the organization slug in the URL, and users may only access tags for organizations they are currently active in.

### Tag Endpoints

- **Assign tags to an object**
  - `POST /api/v1/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/`
  - Example: `/api/v1/orgs/acme-inc/tags/contacts/contact/42/` with body `["vip", "newsletter"]`
- **Remove a tag from an object**
  - `DELETE /api/v1/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/{slug}/`
  - Example: `/api/v1/orgs/acme-inc/tags/contacts/contact/42/vip/`
- **List all tags for an organization**
  - `GET /api/v1/orgs/{org_slug}/tags/`
- **Edit a tag's name**
  - `PATCH /api/v1/orgs/{org_slug}/tags/{tag_id}/` (body: `{ "name": "newname" }`)
- **Delete a tag**
  - `DELETE /api/v1/orgs/{org_slug}/tags/{tag_id}/`

### How it works

- Tags are stored in the `tags` app using the `Tag` and `TaggedItem` models.
- Tag assignment is polymorphic: any model can be tagged by specifying its `app_label`, `model` name, and object ID.
- The system uses Django's ContentTypes to link tags to arbitrary models.
- All tag actions are restricted to the user's current organization (enforced via org slug in the URL and membership checks).

### Example: Tagging a Contact

To assign tags to a contact with ID 42 in organization `acme-inc`:

```http
POST /api/v1/orgs/acme-inc/tags/contacts/contact/42/
Body: ["vip", "newsletter"]
```

To remove the tag `vip` from the same contact:

```http
DELETE /api/v1/orgs/acme-inc/tags/contacts/contact/42/vip/
```

### Notes

- Tags are unique **per organization**. The same tag name or slug can exist in different organizations.
- Tags are always associated with an organization (ForeignKey).
- All tag endpoints require authentication and org membership.
- Only the user's current org is accessible in the API.

## Polymorphic Images (Organization-Scoped)

You can upload images and attach them to any model (contacts, organizations, etc.) using Django's ContentTypes framework. Images are always scoped to the user's current organization. All image API endpoints require the organization slug in the URL, and users may only access images for organizations they are currently active in.

### Image Features

- Upload single or multiple images (bulk upload)
- Automatic generation of multiple .webp versions (thumb, small, medium, large)
- Attach/detach images to any model (polymorphic relation)
- Set cover images, custom alt text, title, and description per relation
- List images for an organization or for a specific object
- Update image metadata (title, description, alt text)
- All endpoints require JWT authentication and enforce org membership

### Image Endpoints

- **Upload image**
  - `POST /api/v1/images/orgs/{org_slug}/images/` (multipart/form-data, field: `file`)
- **Bulk upload images**
  - `POST /api/v1/images/orgs/{org_slug}/bulk-upload/` (multipart/form-data, field: `files`)
- **Bulk delete images**
  - `POST /api/v1/images/orgs/{org_slug}/bulk-delete/` with body `{ "ids": [1,2,3] }`
- **Attach image to any object**
  - `POST /api/v1/images/orgs/{org_slug}/attach/` with body `{ "image_id": 1, "app_label": "contacts", "model": "contact", "object_id": 42 }`
- **Detach image from any object**
  - `POST /api/v1/images/orgs/{org_slug}/detach/` (same payload as attach)
- **Bulk attach/detach to a specific object**
  - `POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_attach/` with body `{ "image_ids": [1,2,3] }`
  - `POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_detach/` with body `{ "image_ids": [1,2,3] }`
- **List images for org or object**
  - `GET /api/v1/images/orgs/{org_slug}/images/`
  - `GET /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/`
- **Update image metadata**
  - `PATCH /api/v1/images/orgs/{org_slug}/images/{image_id}/`

**All API details and schemas are fully documented in the OpenAPI (Swagger) docs.**

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
- This makes onboarding and development simple and fast for new projects and teams.

### How to Tighten Permissions

- To restrict an action to admins/owners, simply swap the `is_member` check for `is_admin` or `is_owner` in the relevant endpoint.
- You can add more granular permission logic as needed, leveraging the existing helpers.

---

For more details, see `organizations/permissions.py` and the usage in API modules like `contacts/api.py`.

## Project Structure

```
DjangoApiStarter/
├── accounts/           # User management & auth
├── organizations/      # Organization management
├── contacts/           # Contact management
├── tags/               # Tag management
├── core/               # Core utilities
├── images/             # Image management
├── api/                # API routers & schemas
├── DjangoApiStarter/   # Project settings
├── manage.py
└── requirements.txt
```

## Contributing

Pull requests are welcome when this is a bit more advanced.
