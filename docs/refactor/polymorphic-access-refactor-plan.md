# Polymorphic Access Refactor Plan

## Context

Tags and images both expose polymorphic routes that accept `app_label`, `model`, and `obj_id`.
Before this cleanup, each route repeated the same flow:

- resolve the organization from `org_slug`
- check organization access
- resolve a `ContentType`
- resolve the model through Django apps
- fetch the object
- verify that the object belongs to the organization

The behavior is reasonable, but the repeated sequence is a security maintenance risk. A future route can easily forget one step.

## Target

Centralize polymorphic object resolution in one helper:

```python
resolve_org_scoped_content_object(request, org_slug, app_label, model, obj_id)
```

The helper should return the organization, content type, model class, and object after access checks have passed.

## Scope

- Add shared resolver helpers under `core/utils/polymorphic.py`.
- Migrate `tags/api.py` and `images/api.py`.
- Keep domain-specific tag/image behavior in each app.
- Preserve existing response shapes and status behavior where practical.

## Deferred

The stable media proxy at `/media/<key>` is still intentionally separate. It currently serves files without object-level auth. That needs a product decision because browser image rendering, cache headers, and JWT-based auth interact awkwardly.

Options for a later pass:

- keep media public by design and document that image filenames are bearer URLs
- move to signed media URLs with expiry
- add authenticated media proxy behavior and adjust clients accordingly

## Testing

Minimum coverage:

- resolver allows org members to resolve org-scoped objects
- resolver rejects non-members
- resolver rejects objects from another organization
- resolver handles unknown app/model and missing object as 404
- existing image and tag permission route tests continue to pass
