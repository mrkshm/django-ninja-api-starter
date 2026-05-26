# API Route Layout Review

Date: 2026-05-26

## Decision

Do not split additional apps into `api/` packages yet.

Use a single `api.py` while an app has a small, coherent route surface. Move to an `api/` package only when the split removes real complexity rather than just moving code around.

## Current App Shape

- `contacts/api.py`: keep. The file is cohesive around contact CRUD and avatar handling.
- `tags/api.py`: keep. Polymorphic object resolution is centralized, so the remaining file is straightforward.
- `images/api/`: keep. This is justified by the number of independent image behaviors.

## Images Review

The images API has been split into `images/api/` modules by behavior:

- `listing.py`: organization and object image listing
- `relations.py`: attach/detach and bulk attach/detach
- `ordering.py`: reorder and cover selection
- `metadata.py`: image metadata patch
- `uploads.py`: single and bulk upload
- `deletion.py`: single and bulk delete
- `common.py`: shared router, logger, and org lookup
- `__init__.py`: router assembly and public compatibility re-exports

Supporting pieces:

- `images/api_schemas.py`: route-local request/response schemas
- `images/throttles.py`: image throttle setup

Existing import compatibility is preserved:

```python
from images.api import router, upload_image, bulk_upload_images
```

## Review Criteria For Future Splits

Split a route module only when at least one of these is true:

- route file exceeds a coherent domain boundary
- tests need to import unrelated route helpers to exercise one behavior
- one file has multiple independent setup concerns
- adding a route requires scrolling through unrelated resource families

Do not split solely because another app uses a package layout.
