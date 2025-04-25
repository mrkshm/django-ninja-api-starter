# Polymorphic Tagging System

This document describes the setup, usage, and functionality of the polymorphic tagging system in this Django Ninja API project.

## Overview

The tagging system allows you to assign tags to any model in the system using Django's ContentTypes framework. Tags are **unique per organization** and can be attached to any model that has an `organization` field.

- Tags are stored in the `tags` app using the `Tag` and `TaggedItem` models.
- Tag assignment is polymorphic: any model can be tagged by specifying its `app_label`, `model` name, and object ID.
- The system uses Django's ContentTypes to link tags to arbitrary models.

## Tag Model

- Each tag belongs to an **organization** (`organization` is a ForeignKey to Organization).
- Tags are unique by (`organization`, `name`) and (`organization`, `slug`).
- Slugs are generated automatically from the tag name using Django's `slugify` utility.

## Requirements for Taggable Models

Any model you wish to tag **must** have an `organization` field (ForeignKey to Organization).

## API Endpoints (Organization-Scoped)

All tag endpoints are now scoped to the user's current organization and require the organization slug in the URL. Users may only manage tags for organizations they are a member of and have selected as their current org.

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

## Example Usage

### Assign tags to a contact in an organization

```http
POST /api/v1/orgs/acme-inc/tags/contacts/contact/42/
Body: ["vip", "newsletter"]
```

### Remove a tag from a contact in an organization

```http
DELETE /api/v1/orgs/acme-inc/tags/contacts/contact/42/vip/
```

### Tag API Response Example

```json
{
  "id": 1,
  "name": "vip",
  "slug": "vip",
  "organization": 2
}
```

## Notes

- Tags are unique **per organization**. The same tag name or slug can exist in different organizations.
- The tag model has an `organization` field (ForeignKey to Organization). Tags are always associated with an organization.
- Any model you wish to tag must have an `organization` field.
- API responses for tags include the `organization` field (the organization's ID).
- All tag endpoints require authentication and org membership.
- Only the user's current org (selected via org switcher) is accessible in the API.
- When creating a tag, the slug is generated automatically from the tag name using Django's `slugify` utility.
- `app_label` is the Django app name (e.g. `contacts`).
- `model` is the lowercased model name (e.g. `contact`).
- You can tag any model that supports generic relations.

## Testing

- The test suite includes checks to ensure that tags are unique per organization, and that the same tag name can exist in different organizations.
- Attempting to create a duplicate tag (same name and organization) will raise an integrity error.

---

For more details, see the implementation in the `tags` app and the example tests in `tags/tests/test_tagging_contacts.py`.
