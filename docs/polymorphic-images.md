images will be uploaded to R2 or another S3-compatible storage service.

The original image will be stored, and 4 .webp versions will be generated:

- Thumbnail 160x160, 65% quality
- Small 640x640, 80% quality
- Medium 1024x1024, 85% quality
- Large 2048x2048, 85% quality

The image name will be generated with the generate_upload_filename helper function (in core/utils/utils.py). The name will be used for the original image. For the versions, the name will be used with the suffix '\_thumb', '\_sm', '\_md', and '\_lg'.

Images should have:

- an optional description
- an optional alt text
- an optional title

The relation should have:

- a boolean is_cover default false
- order (integer, optional)
- custom_description (string, optional)
- custom_alt_text (string, optional)
- custom_title (string, optional)

---

## Implementation Plan: Polymorphic Images

This plan outlines step-by-step how to implement polymorphic images with Django, S3-compatible storage, and automatic image versioning. Each step builds on the previous one.

### 1. Create the `images` App and Models

- Create a new Django app called `images`.
- Implement the `Image` model with fields:
  - `file` (image upload)
  - `description` (optional)
  - `alt_text` (optional)
  - `title` (optional)
  - Timestamps (`created_at`, `updated_at`)
- Implement the polymorphic relation model (e.g., `PolymorphicImageRelation`) using Django's contenttypes framework:
  - ForeignKey to `Image`
  - GenericForeignKey to any model
  - `is_cover` (boolean, default False)
  - `order` (integer, optional)
  - `custom_description`, `custom_alt_text`, `custom_title` (all optional)

### 2. Configure Storage

- Set up S3-compatible storage (e.g., Cloudflare R2) in Django settings using `django-storages`.
- Configure media storage backend and permissions.

### 3. Implement Image Upload & File Naming

- Use the `generate_upload_filename` helper for consistent naming.
- Ensure uploaded images are saved to the correct location in storage.

### 4. Generate Image Versions

- On image upload, automatically generate 4 .webp versions:
  - Thumbnail (160x160, 65% quality)
  - Small (640x640, 80% quality)
  - Medium (1024x1024, 85% quality)
  - Large (2048x2048, 85% quality)
- Use a library like Pillow for processing and saving versions.
- Store versioned images with appropriate suffixes (`_thumb`, `_sm`, `_md`, `_lg`).
- Use `upload_to_storage` helper function from `core.utils.storage`.

### 5. Expose API Endpoints

- Use Django Ninja to create API endpoints for:
  - Uploading images
  - Listing images and their versions
  - Attaching/detaching images polymorphically to any model
  - Updating relation fields (is_cover, order, overrides)

### 6. Permissions & Validation

- Add appropriate permissions for uploading, attaching, and modifying images.
- Validate image types and sizes on upload.

### 7. Documentation & Examples

- Document API endpoints, expected payloads, and example responses.
- Add usage examples for attaching images polymorphically.

---

## Updated API Endpoints (2025)

The following reflects the **latest endpoints and behaviors** for polymorphic image management as implemented in the codebase:

### Upload Image

- **POST** `/api/v1/images/orgs/{org_slug}/images/`
  - Upload a single image file (multipart/form-data, field: `file`).
  - Returns serialized image info on success, 400 with error on failure.
  - **Response:**
    ```json
    {
      "id": 1,
      "file": "images/img_xxxxx.png",
      "description": null,
      "alt_text": null,
      "title": "filename.png",
      "organization_id": 2,
      "creator_id": 3,
      "created_at": "2025-04-27T16:00:00Z",
      "updated_at": "2025-04-27T16:00:00Z"
    }
    ```

### Bulk Upload Images

- **POST** `/api/v1/images/orgs/{org_slug}/bulk-upload/`
  - Upload multiple images at once (multipart/form-data, field: `files`).
  - Returns a list of status objects for each file.
  - **Response:**
    ```json
    [
      { "status": "success", "id": 1, "file": "images/img_xxxx.png" },
      { "status": "error", "error": "File too large", "file": "bigfile.png" }
    ]
    ```

### Bulk Delete Images

- **POST** `/api/v1/images/orgs/{org_slug}/bulk-delete/`
  - Delete multiple images by IDs.
  - **Payload:** `{ "ids": [1, 2, 3] }`
  - Returns 204 on success, 400 with error if no IDs or invalid data.

### Attach/Detach Image Polymorphically

- **POST** `/api/v1/images/orgs/{org_slug}/attach/`

  - Attach an image to any object (provide `image_id`, `app_label`, `model`, `object_id`).
  - **Payload:**
    ```json
    {
      "image_id": 1,
      "app_label": "contacts",
      "model": "contact",
      "object_id": 42
    }
    ```
  - **Response:** `{ "detail": "attached", "created": true }`

- **POST** `/api/v1/images/orgs/{org_slug}/detach/`
  - Detach an image from an object (same payload as attach).
  - Returns 204 on success.

### Bulk Attach/Detach (Per Object)

- **POST** `/api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_attach/`
- **POST** `/api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_detach/`
  - Attach/detach multiple images to/from a single object.
  - **Payload:** `{ "image_ids": [1, 2, 3] }`
  - **Response:** `{ "attached": [1,2,3] }` or `{ "detached": [1,2,3] }`

### List Images

- **GET** `/api/v1/images/orgs/{org_slug}/images/` — All images for org
- **GET** `/api/v1/images/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/` — Images for a specific object

### Edit Image Metadata

- **PATCH** `/api/v1/images/orgs/{org_slug}/images/{image_id}/`
  - Update title, description, alt text, etc.

---

## Model/Schemas Overview

- **Image**: file, description, alt_text, title, organization, creator, created_at, updated_at
- **PolymorphicImageRelation**: image, content_type, object_id, is_cover, order, custom_description, custom_alt_text, custom_title
- **ImageOut Schema**: All API responses use Pydantic serialization; file and datetime fields are always strings.

---

## Notes on Usage

- All endpoints require authentication and organization membership.
- All error responses are returned as JSON with appropriate status codes (400, 403, 404, etc).
- Bulk endpoints now use POST (not DELETE) and expect JSON or multipart/form-data as appropriate.
- File uploads must use the correct field names (`file` for single, `files` for bulk).
- Attach/detach endpoints are generic and work for any model via contenttypes.

---
