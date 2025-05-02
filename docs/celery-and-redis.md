# Celery & Redis Integration

## Purpose

Celery and Redis are used in this project for:

- **Asynchronous email sending** (e.g., password reset, notifications)
- **Organization data export** (GDPR-compliant, async, delivered via signed link)
- **Scheduled cleanup tasks** (e.g., removing orphaned images/tags)
- **Caching authentication and permissions** (fast org membership checks)

## Setup

- Redis is used as both the Celery broker and Django cache backend.
- Configure `CELERY_BROKER_URL` and `CACHES` in `settings.py` to use Redis.
- Start Celery workers: `celery -A DjangoApiStarter worker -l info`
- (Optional) Start Flower for monitoring: `celery -A DjangoApiStarter flower`

## Functionality Using Redis and Celery

### 1. Asynchronous Email Sending

- Password reset and notification emails are sent via Celery tasks.
- All email delivery is handled asynchronously to avoid blocking API requests.

### 2. Organization Data Export

- Org admins can trigger a full data export via API.
- Export runs as a Celery task, packages all org data (users, contacts, images, tags, etc.) as JSON, zips it, and uploads to S3 (or configured storage).
- User receives a signed download link (valid for 7 days) via email.
- Export files are automatically deleted after expiry (via S3 lifecycle or scheduled cleanup).

### 3. Scheduled Cleanup Tasks

- Celery Beat is used for periodic jobs (e.g., weekly cleanup of orphaned images/tags).
- All scheduled tasks are robust and safe to run in production.

### 4. Authentication & Permission Caching

- Organization membership and permission checks (`is_member`, `is_admin`, `is_owner`) are cached in Redis for 1 hour to reduce database load.
- Cache invalidation is handled via Django signals when memberships change.

## Best Practices

- Secure Redis in production (AUTH/TLS).
- Monitor Celery workers and Redis health.
- Implement proper cache invalidation and timeouts.

## References

- [Celery Docs](https://docs.celeryq.dev/en/stable/)
- [Django Ninja Async Tasks](https://django-ninja.dev/guides/background-tasks/)
- [Redis Quickstart](https://redis.io/docs/getting-started/)
