# Private Image Storage Strategy

Date: 2026-05-27

## Decision

Use Cloudflare R2 with separate private and public buckets from the start.

Image files should be private by default, readable only through application-controlled access:

- authenticated org-member access for normal app use
- explicit share links for outside-org access
- short-lived signed R2 URLs for direct client downloads
- explicit public visibility for intentionally public/admin content

Do not rely on stable public `/media/<key>` URLs for product images.

Recommended bucket split:

```text
R2_PRIVATE_BUCKET_NAME
  orgs/{org_id}/images/...
  avatars/...
  uploads/...

R2_PUBLIC_BUCKET_NAME
  public/images/...
  admin/content/...
```

`IMAGE_PUBLIC_BASE_URL` should point only at the public bucket's custom domain/CDN.

## API Model

- API uploads are private by default.
- Private images expose `variant_keys` and are fetched through signed URL endpoints.
- Public images are explicit through `Image.visibility = "public"`.
- Public images expose `public_url` and `public_variant_urls` when `IMAGE_PUBLIC_BASE_URL` is configured.
- `/media/<key>` is disabled by default and only available when `ALLOW_UNAUTHENTICATED_MEDIA_SERVE=True`.

## Endpoints

Authenticated org-member access:

```text
GET /api/v1/images/orgs/{org_slug}/images/{image_id}/urls
```

Share links:

```text
POST /api/v1/images/orgs/{org_slug}/images/{image_id}/shares
GET /api/v1/images/shared/images/{token}/urls
DELETE /api/v1/images/orgs/{org_slug}/images/{image_id}/shares/{share_id}
```

## iOS Caching

Signed URLs do not prevent device caching.

The app should not key durable cache entries by signed URL because signatures change. Prefer:

```text
image_id + variant + updated_at
```

or:

```text
image_id + variant + content_hash
```

## Settings

```env
R2_PRIVATE_BUCKET_NAME=...
R2_PUBLIC_BUCKET_NAME=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_ENDPOINT_URL=...
IMAGE_PUBLIC_BASE_URL=https://media.example.com
IMAGE_SIGNED_URL_TTL_SECONDS=900
IMAGE_SHARE_LINK_DEFAULT_TTL_SECONDS=604800
```
