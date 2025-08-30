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

## Stable Media Proxy and Variants

To ensure image URLs do not expire and remain cacheable, the backend exposes a stable media proxy and returns relative URLs in API responses.

### Media Proxy

- Endpoint: `GET /media/<path:key>`
- View: `images.views.media_serve`
- URL config: registered in `DjangoApiStarter/urls.py` as `path("media/<path:key>", media_serve, name="media-serve")`
- Behavior: streams files from `default_storage` with long-lived cache headers (`Cache-Control: public, max-age=31536000, immutable`).

### API Response Format

- Image responses include `url` and a `variants` object: `{ original, thumb, sm, md, lg }`.
- All fields are stable, relative paths under `/media/`.
- Filenames follow: `<base>_thumb.webp`, `<base>_sm.webp`, `<base>_md.webp`, `<base>_lg.webp`.
- If a variant file is missing, the API falls back to the original URL for that variant. This guarantees all variant fields are strings and avoids nulls in clients that validate types strictly.

### Variant Generation on Upload

- On single and bulk image uploads, the server generates WebP variants using `core/utils/image.py::resize_images()`:
  - `thumb`: 160x160, 65% quality
  - `sm`: 640x640, 80% quality
  - `md`: 1024x1024, 85% quality
  - `lg`: 2048x2048, 85% quality
- Variants are uploaded alongside the original to storage with the naming convention above.

### Backfilling Existing Images

Use the management command to generate missing variants for existing images:

```
python manage.py backfill_image_variants --verbose
python manage.py backfill_image_variants --org 2 --verbose
python manage.py backfill_image_variants --ids 10 12 15 --verbose
python manage.py backfill_image_variants --org 2 --dry-run --verbose
```

Notes:
- Only missing variants are generated; existing files are skipped.
- Add `--limit N` to process a subset.

### Frontend Integration Notes

- Client code should treat these URLs as relative and prefix with the API base URL when needed.
- Use smaller variants (`thumb` for grids, `md`/`lg` for viewers) and rely on the API to fall back to `original` when variants are unavailable.
- Because URLs are stable and cacheable, placing a CDN in front of the API can significantly improve performance.

### Security Considerations

- The media proxy currently serves files without auth checks. If your use case requires access control, add authentication/authorization in `media_serve` before streaming files.
