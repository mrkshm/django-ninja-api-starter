# API Route Layout Review

Date: 2026-05-26

## Decision

Do not split additional apps into `api/` packages yet.

Use a single `api.py` while an app has a small, coherent route surface. Move to an `api/` package only when the split removes real complexity rather than just moving code around.

## Current App Shape

- `contacts/api.py`: keep. The file is cohesive around contact CRUD and avatar handling.
- `tags/api.py`: keep. Polymorphic object resolution is centralized, so the remaining file is straightforward.
- `images/api.py`: keep for now, but it is the next candidate for a package split.

## Images Review

After extracting image response serialization, `images/api.py` is smaller and easier to scan, but it still combines several concerns:

- listing organization images
- listing/attaching/detaching object relations
- relation order and cover selection
- image metadata updates
- single and bulk upload
- single and bulk delete
- rate-limit configuration
- validation error override

That is enough to justify a future split, but not immediately. The media URL policy is now settled as public bearer-style URLs with deterministic variant paths, so future image cleanup should focus on behavior boundaries rather than storage URL checks.

- tighten bulk delete/upload error semantics
- split only if a specific behavior area becomes hard to change safely

Splitting before a concrete behavior problem appears would likely move stable code between files and create extra import churn.

## Future Split Shape

If `images/api.py` keeps growing, split it by behavior:

```text
images/api/
  __init__.py      # router assembly and public re-exports for compatibility
  routes.py        # shared router/throttle setup, if needed
  listing.py       # org and object list routes
  relations.py     # attach/detach/reorder/cover routes
  uploads.py       # upload and bulk upload
  metadata.py      # image metadata patch
  deletion.py      # delete and bulk delete
```

Keep existing import compatibility during the migration:

```python
from images.api import router, upload_image, bulk_upload_images
```

Tests and callers currently import route callables directly from `images.api`, so `__init__.py` should re-export those names until tests and any external code are migrated.

## Review Criteria For Future Splits

Split a route module only when at least one of these is true:

- route file exceeds a coherent domain boundary
- tests need to import unrelated route helpers to exercise one behavior
- one file has multiple independent setup concerns
- adding a route requires scrolling through unrelated resource families

Do not split solely because another app uses a package layout.
