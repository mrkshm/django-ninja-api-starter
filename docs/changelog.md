# 2025 / 08
## API TODOs (Images & Polymorphic Attachments)

- [x] Unify response schemas and status codes
  - [x] Define request/response Schemas for:
    - [x] Attach to object: POST `/images/{app_label}/{model}/{obj_id}/` (ImageIdsIn -> List[PolymorphicImageRelationOut])
    - [x] Remove from object: DELETE `/images/{app_label}/{model}/{obj_id}/{image_id}/` (204 No Content)
    - [x] Bulk attach/detach: explicit input/output Schemas with lists of attached/detached ids
  - [x] Ensure all mutation endpoints return 200 with body or 204 with no body consistently

- [x] Normalize list endpoints
  - [x] [list_images_for_org](cci:1://file:///Users/mrks/Code/TurboStarter/DjangoApiStarter/images/api.py:49:0-61:18): return serialized `ImageOut` (not `.values()` dicts) for consistency
  - [x] Confirm pagination/ordering parameters are documented and tested (Images done; Tags list uses LimitOffset with `?limit`/`?offset` — add docs examples)

- [x] Metadata update contract
  - [x] Define a proper Schema for `PATCH /images/{image_id}/` (`ImagePatchIn` with `title`, `description`, `alt_text`)
  - [x] Validate fields and restrict unknown attributes instead of blindly setting any attribute

- [x] Ordering and “primary”
  - [x] Implemented on relation (`PolymorphicImageRelation`): `is_cover` and `order` with DB partial unique constraint (single primary per object) and index
  - [x] Added `POST /images/{app_label}/{model}/{obj_id}/reorder` with `{ image_ids: number[] }` (full list required; first becomes primary)

- [x] Bulk operations
  - [x] Add idempotency support (e.g., `Idempotency-Key` header) for `bulk-upload`, `bulk-delete`, `bulk_attach`, `bulk_detach`
  - [x] Wrap bulk operations in transactions where applicable

- [x] Upload flow safeguards
  - [x] Document/centralize max size (10MB) and allowed MIME types (image/* whitelist)
  - [ ] Deferred: integrate virus scanning / EXIF stripping / content moderation flags
  - [x] Return variant URLs or a predictable path scheme for `thumb/sm/md/lg`

- [x] Permissions and audit
  - [x] Ensure `check_contact_member`/org membership is applied uniformly across all endpoints
  - [x] Add audit logging on attach/detach/delete operations (user, org, object)
  - [x] Permission tests per route (non-member forbidden, cross-org rejected)
    - [x] Tags: all endpoints (list/search, by-slug, list for object, assign, update, delete, bulk unassign, unassign by slug)
    - [x] Contacts: get/update/patch/delete, avatar upload/delete, create with foreign org
    - [x] Images: GET `/orgs/{org_slug}/images/` (non-member -> 403)
    - [x] Images: POST `/orgs/{org_slug}/bulk-upload/` (non-member -> 403)
    - [x] Images: POST `/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/bulk_attach/` (cross-org image id -> 403)
    - [x] Images: GET `/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/` (non-member -> 403, object not in org -> 403)
    - [x] Images: POST `/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/` attach (non-member -> 403)
    - [x] Images: DELETE `/orgs/{org_slug}/images/{app_label}/{model}/{obj_id}/{image_id}/` remove (non-member -> 403)
    - [x] Images: PATCH `/orgs/{org_slug}/images/{image_id}/` edit metadata (non-member -> 403)
    - [x] Images: DELETE `/orgs/{org_slug}/images/{image_id}/` delete (non-member -> 403)
    - [x] Images: POST `/orgs/{org_slug}/bulk-delete/` (non-member -> 403)

- [x] Error handling consistency
  - [x] Keep 400 for validation errors (custom Ninja handler already in place)
  - [x] Normalize error shapes: `{ detail: string }` across endpoints

- [x] OpenAPI/docs/tests
  - [x] Update OpenAPI/Swagger docs to reflect removed org-level attach/detach and unified responses/variants in docs
  - [x] Document Tags assign-by-name and single unassign-by-slug routes in docs/api-routes.md
  - [x] Contacts: expose `organization` and `creator` fields (slugs) in responses via schema aliasing
  - [x] Add tests:
    - [x] Attach/detach single and bulk paths
    - [x] Permissions checks (wrong org / wrong object)
    - [x] Upload errors (size/type)
    - [x] Upload success
    - [x] Deletion removes storage variants
  - [x] Add examples for all endpoints under Images in [docs/api-routes.md](cci:7://file:///Users/mrks/Code/TurboStarter/DjangoApiStarter/docs/api-routes.md:0:0-0:0)
  - [x] Document Idempotency-Key usage for bulk endpoints in docs/api-routes.md
  - [x] Document relation ordering, primary behavior, and reorder endpoint in docs/api-routes.md

- [x] Future consideration
  - [x] Rate limiting for upload and bulk endpoints
    - [x] Implement per-user throttles configurable via settings
    - [x] Add tests asserting 429 after first allowed request for single and bulk upload