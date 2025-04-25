# django-ninja-api-starter

A starter template for building fast, secure REST APIs with [Django Ninja](https://django-ninja.dev) and Django.

Featuring Django, Django Ninja, Pydantic, Celery, Orjson, Pillow, ImageKit... all that good stuff.

## Getting Started

This is still a work in progress. But if you want to poke around, go ahead.

## Features

- Django Ninja for high-performance API development
- JWT authentication (with Ninja Extra)
- Modular app structure
- Ready-to-use user model, polymorphic tags and authentication
- Interactive API documentation
- Pytest and built-in API tests

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
- [ ] Celery for background tasks
- [ ] Docker setup
- [ ] Easy deployment with Kamal
- [ ] Postman collection for API testing

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

## Quick Start

```bash
# Clone the repo
$ git clone https://github.com/mrkshm/django-ninja-api-starter.git
$ cd django-ninja-api-starter

# Create a virtual environment and activate it
$ python3 -m venv venv
$ source venv/bin/activate

# Install dependencies
$ pip install -r requirements.txt

# Apply migrations
$ python manage.py migrate

# Run the development server
$ python manage.py runserver
```

Visit [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs) for interactive API documentation.

## Project Structure

```
DjangoApiStarter/
├── accounts/           # User management & auth
├── contacts/           # Contact management
├── core/               # Core utilities
├── organizations/      # Organization management
├── api/                # API routers & schemas
├── DjangoApiStarter/   # Project settings
├── tests/              # Pytest-based tests
├── manage.py
└── requirements.txt
```

## Contributing

Pull requests are welcome when this is a bit more advanced.
