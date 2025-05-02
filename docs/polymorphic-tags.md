# Polymorphic Tags in DjangoApiStarter

## What Are Polymorphic Tags?

Polymorphic tags allow you to assign tags to any type of object in your Django project, not just a single model. This is achieved using Django's contenttypes framework, which enables a generic relationship between tags and any other model instance.

This approach enables:
- Tagging any model (contacts, projects, images, etc.)
- Centralized tag management per organization
- Flexible querying and filtering by tags across the project

## Requirements for Taggable Models

Any model you wish to tag **must** have an `organization` field (ForeignKey to Organization). Tags are always associated with an organization.

## How It Works in This App

The implementation is found in `tags/models.py` and consists of two main models:

### 1. `Tag`

Represents a tag within an organization.

**Fields:**
- `organization`: ForeignKey to the owning organization
- `name`: Tag name (unique within org)
- `slug`: Slugified tag name (unique within org, generated automatically from the tag name using Django's `slugify` utility)

**Meta:**
- Unique together: (`organization`, `name`) and (`organization`, `slug`) ensure tags are unique per org

### 2. `TaggedItem`

Defines a generic (polymorphic) relationship between a `Tag` and any other model instance.

**Fields:**
- `tag`: ForeignKey to the `Tag`
- `content_type`, `object_id`, `content_object`: The generic foreign key to any model instance

**Meta:**
- Unique together: (`tag`, `content_type`, `object_id`) ensures a tag can only be attached once to a given object

## Usage in the API

- All tag endpoints require authentication and organization membership.
- All endpoints are scoped to the user's current organization and require the org slug in the URL. Users may only manage tags for organizations they are a member of and have selected as their current org.
- Tags can be listed, created, updated, deleted, and assigned/unassigned to any model that supports tagging.
- Assign/unassign endpoints are generic (accept `app_label`, `model`, and `object_id`).
- Bulk tag assignment is supported.
- API responses for tags include the `organization` field (the organization's ID).
- The `app_label` is the Django app name (e.g. `contacts`), and `model` is the lowercased model name (e.g. `contact`).
- All error responses are returned as JSON with appropriate status codes.

## Example: Assigning a Tag to Any Object

To assign a tag to a model instance (e.g., a `Contact` or `Image`):
- Use the API endpoint: `POST /api/v1/orgs/{org_slug}/tags/{app_label}/{model}/{obj_id}/`
- Provide the tag slug(s) and any additional metadata as needed.

## Why Use Polymorphic Tags?

- Enables flexible, DRY code for tagging across the project
- Makes it easy to add tag support to new models without schema changes
- Centralizes tag management and querying

## Testing and Integrity

- The test suite ensures tags are unique per organization and that the same tag name can exist in different organizations.
- Attempting to create a duplicate tag (same name and organization) will raise an integrity error.

## References

- See `tags/models.py` for implementation details
- See API docs for endpoint details and usage examples
