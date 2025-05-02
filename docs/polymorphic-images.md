# Polymorphic Images in DjangoApiStarter

## What Are Polymorphic Images?

Polymorphic images are images that can be attached to any model in the Django project, not just a single type (like "Profile" or "Product"). This is achieved using Django's contenttypes framework, which enables a generic relationship between images and any other model instance.

This approach allows you to:

- Attach the same image to multiple different objects (of any model)
- Store additional metadata about the image-object relationship (e.g., is this the cover image? Custom alt text?)
- Support ordering, per-object customizations, and efficient querying

## How It Works in This App

The implementation is found in `images/models.py` and consists of two main models:

### 1. `Image`

Represents an uploaded image file and its global metadata.

**Fields:**

- `file`: The image file itself
- `description`, `alt_text`, `title`: Optional descriptive metadata
- `organization`: ForeignKey to the owning organization
- `creator`: User who uploaded the image
- `created_at`, `updated_at`: Timestamps

### 2. `PolymorphicImageRelation`

Defines a generic (polymorphic) relationship between an `Image` and any other model instance.

**Fields:**

- `image`: ForeignKey to the `Image`
- `content_type`, `object_id`, `content_object`: The generic foreign key to any model instance
- `is_cover`: Boolean, whether this image is the cover for the object
- `order`: Integer, for ordering images on the object
- `custom_description`, `custom_alt_text`, `custom_title`: Per-object image metadata

**Meta:**

- Unique together: (`image`, `content_type`, `object_id`) ensures an image can only be attached once to a given object
- Default ordering: by `order`, then `pk`

## Usage in the API

- All image endpoints require authentication and organization membership.
- Images can be attached, detached, listed, and updated for any model that supports images.
- Attach/detach endpoints are generic (accept `app_label`, `model`, and `object_id`).
- Bulk operations are supported for attaching/detaching multiple images.
- File uploads use the `file` (single) or `files` (bulk) field names.
- All error responses are returned as JSON with appropriate status codes.

## Example: Attaching an Image to Any Object

To attach an image to a model instance (e.g., a `Contact` or `Project`):

- Use the API endpoint: `POST /api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/`
- Provide the image file and any custom metadata as needed.

## Why Use Polymorphic Images?

- Enables flexible, DRY code for image handling across the project
- Makes it easy to add image support to new models without schema changes

## References

- See `images/models.py` for implementation details
- See API docs for endpoint details and usage examples
