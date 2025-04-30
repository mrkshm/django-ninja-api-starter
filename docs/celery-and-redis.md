# Celery & Redis Integration Guide

This guide covers how to set up background tasks in your Django Ninja API using Celery and Redis, including best practices and deployment notes.

## Current Progress

✅ **Completed Steps:**

1. **Redis Installation & Configuration**

   - Redis is installed and running in Docker
   - Using Redis 7-alpine image
   - Configured as both Celery broker and Django cache backend

2. **Celery Setup**

   - Celery is installed and configured
   - Using Redis as broker and result backend
   - Worker and beat services running in Docker
   - Health checks implemented

3. **Basic Infrastructure**

   - Docker setup complete
   - Development and production modes configured
   - Services properly linked and dependent

4. **Redis Caching for Permissions**

   - Redis is configured as the Django cache backend using `django_redis` in `settings.py`.
   - Permission checks for organization membership (`is_member`, `is_admin`, `is_owner`) now use Redis to cache results for 1 hour, reducing DB load and improving API performance.
   - Cache invalidation is robust:
     - When a user's membership is added or removed, Django signals automatically clear the relevant cache keys.
     - This ensures permission checks always reflect the latest state.
   - Tests cover caching and invalidation:
     - Tests verify that cache keys are set, updated, and cleared as expected when memberships change.

5. **Authentication and Membership Caching**

   - User permissions (e.g., `get_user_permissions()`) and organization membership checks (`is_member`, `is_admin`, `is_owner`) are now cached in Redis for fast access.
   - Cache invalidation is handled via Django signals, ensuring up-to-date permission checks.
   - Thoroughly tested with Pytest for both caching and invalidation.

6. **Scheduled Cleanups**
   - Orphaned image cleanup: Implemented a Celery task and scheduled it via Celery Beat to run weekly.
   - Orphaned tag cleanup: Implemented a Celery task and scheduled it via Celery Beat to run weekly.
   - All cleanup tasks are robust, safe, and run automatically.

## Next Steps

### 1. Implement a Celery Background Task

Now that authentication and membership caching is complete, the next step is to leverage Celery for background tasks. Recommended use cases:

- **Asynchronous Email Sending**

  - Offload password reset, account confirmation, and notification emails
  - Handle retries and error cases

- **GDPR-Compliant User Data Export**

  - Implement background task for user data export
  - Handle large datasets efficiently

- **Implementing a Data Export Function (High-Level Plan)**

  1. **Define Export Requirements**

  - What data should be exported (e.g., users, organizations, tags, images)?
  - In what format (CSV, JSON, Excel, ZIP, etc.)?
  - Who can trigger exports (admins, users, API, etc.)?
  - Where should the exported file go (local file, S3, email, download link, etc.)?

  2. **Create the Export Function**

  - Write a function to gather the required data, serialize it, and save it to a file.

  3. **Wrap the Export in a Celery Task**

  - Move the export logic into a Celery `@shared_task` so it runs in the background.

  4. **Trigger the Export**

  - Provide a trigger mechanism (admin action, API endpoint, or management command).

  5. **Notify User or Make Export Available**

  - Notify user when the export is complete (email, in-app, or download link).
  - Store the export file in a discoverable location (e.g., FileField or S3 URL).

  6. **(Optional) Schedule Regular Exports**

  - Use Celery Beat to schedule exports (nightly, weekly, etc.) if needed.

  7. **Testing**

  - Write tests for export logic, Celery task execution, and permissions.

---

Let the team know your preferred export format and trigger, and the export function can be scaffolded quickly!

---

## Implementation Details

### Authentication Caching Strategy

1. **Cache Keys**

   - Use consistent naming: `{resource_type}_{id}_{purpose}`
   - Example: `user_permissions_123`, `user_orgs_456`

2. **Cache Invalidation**

   - Invalidate cache on user permission changes
   - Invalidate on organization membership changes
   - Use signals to handle cache invalidation

3. **Cache Timeouts**
   - Short timeouts for frequently changing data (e.g., 5-15 minutes)
   - Longer timeouts for stable data (e.g., 1 hour)
   - Consider using versioned cache keys for complex invalidation

### Monitoring & Maintenance

1. **Cache Health**

   - Monitor cache hit/miss ratios
   - Track memory usage
   - Set up alerts for cache failures

2. **Performance Metrics**
   - Measure response times with/without cache
   - Track cache effectiveness
   - Monitor Redis memory usage

## Best Practices & Tips

- Use environment variables for Redis URLs and Celery config
- Secure sensitive data in transit (use Redis AUTH and/or TLS for production)
- Monitor Celery workers and queue health in production
- Use retry logic and error handling in Celery tasks
- For periodic tasks, use `django-celery-beat`
- Implement proper cache invalidation strategies
- Use appropriate cache timeouts based on data volatility
- Monitor cache performance and adjust as needed

---

## Recent Accomplishments: Redis Caching for Permissions

### What We Implemented

- **Redis is configured as the Django cache backend** using `django_redis` in `settings.py`.
- **Permission checks for organization membership** (`is_member`, `is_admin`, `is_owner`) now use Redis to cache results for 1 hour, reducing DB load and improving API performance.
- **Cache invalidation is robust:**
  - When a user's membership is added or removed, Django signals automatically clear the relevant cache keys.
  - This ensures permission checks always reflect the latest state.
- **Tests cover caching and invalidation:**
  - Tests verify that cache keys are set, updated, and cleared as expected when memberships change.

### Example: How Permission Caching Works

```python
# Check if user is a member (organizations/permissions.py)
def is_member(user, org):
    cache_key = f'is_member_{user.id}_{org.id}'
    result = cache.get(cache_key)
    if result is None:
        result = Membership.objects.filter(user=user, organization=org).exists()
        cache.set(cache_key, result, timeout=3600)
    return result
```

### Example: How Cache Is Invalidated

```python
# Invalidate on membership change (organizations/signals.py)
@receiver([post_save, post_delete], sender=Membership)
def invalidate_membership_cache(sender, instance, **kwargs):
    user_id = instance.user_id
    org_id = instance.organization_id
    for kind in ["is_owner", "is_admin", "is_member"]:
        cache_key = f"{kind}_{user_id}_{org_id}"
        cache.delete(cache_key)
```

### Example: Test for Caching and Invalidation

```python
# Test that cache is set, invalidated, and updated
def test_is_member_cache_invalidation():
    ...
    assert is_member(user, org) is True  # Cache set to True
    ...
    Membership.objects.filter(user=user, organization=org).delete()
    ...
    assert is_member(user, org) is False  # Cache updated to False
```

### Why This Matters

- **Performance:** Most permission checks are now instant after the first DB hit.
- **Correctness:** Cache is always up-to-date with membership changes.
- **Scalability:** Ready for high-traffic APIs with many permission checks per request.

---

For more details, see `organizations/permissions.py`, `organizations/signals.py`, and the tests in `organizations/tests/test_permissions.py`.

## High-Level Steps

1. **Install Redis**

   - Redis is used as both the Celery broker and Django cache backend.
   - Install Redis locally (or use a managed service in production).

2. **Configure Redis as Django Cache**

   - Use Django's cache framework with Redis for fast access to user/org/auth info.
   - Configure in `settings.py`:
     ```python
     CACHES = {
         "default": {
             "BACKEND": "django_redis.cache.RedisCache",
             "LOCATION": "redis://127.0.0.1:6379/1",
             "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
         }
     }
     ```
   - Consider cache invalidation for sensitive data.

3. **Install & Configure Celery**

   - Install Celery and set it up to use Redis as the broker (and optionally as the result backend).
   - Add a `celery.py` in your project root and ensure it loads on Django startup.
   - Update requirements and document the setup.

4. **Choose a Celery Use Case**

   - Example: GDPR-compliant user data export ("Right to Access").
   - Other ideas: sending emails, generating reports, scheduled cleanups.
   - **Scheduled cleanups:**
     - Check for images without a `polymorphic_image_relation` and remove them.
     - Remove tags (including polymorphic tags) that no longer have any tag relations.

5. **Implement the Background Task**

   - Write a Celery task for your use case (e.g., gather and package user data).
   - Add an API endpoint to trigger the task and check its status.
   - Optionally, notify the user when the task is complete.

6. **Add Documentation & Deployment Info**
   - Document how to run Celery locally and in production.
   - Add a health check endpoint for Celery.
   - Consider using `django-celery-beat` for scheduled tasks.
   - Document how to run Django, Celery workers, and optionally Celery beat in production.

---

## Data Export Function Requirements (as discussed)

- **Scope:** Organization-scoped export. An org admin (or user with permission) can export all data belonging to their organization.
- **Included Data:**
  - All users/members of the organization (with email, name, role, language, etc.)
  - All organization domain entities (contacts, images, tags, etc.)
  - Creator/owner fields for each entity
  - All relevant audit fields (timestamps, etc.)
- **Format:** JSON (for structured data), zipped for compression. If needed, multiple files (e.g., data.json, images/) can be included in the zip.
- **Delivery:**
  - Export file is uploaded to S3 (or the configured storage backend)
  - User receives a signed download link (valid for a limited time)
  - No email attachments (to avoid size limits)
- **Trigger:** Export is requested by an org admin (via UI or API). Only users with appropriate org permissions can trigger the export.
- **Notification:** User is notified (email or in-app) when the export is ready, with the download link.
- **Retention:** Export files are retained for 7 days after creation, then automatically deleted. For S3 storage, this is enforced using an S3 bucket lifecycle policy.
- **Security:** Only authorized users can access the export. Signed URLs expire after a set period.

---

## Summary Table

| Step | Task                       | Notes                     |
| ---- | -------------------------- | ------------------------- |
| 1    | Install Redis              | As broker & cache         |
| 2    | Configure Redis cache      | For user/org/auth info    |
| 3    | Install & configure Celery | Use Redis as broker       |
| 4    | Pick use case              | GDPR data export is great |
| 5    | Implement task & endpoint  | Trigger, status, notify   |
| 6    | Add docs & deployment info | For Celery & Redis        |

---

## Recommended Example Use Cases to Implement

For a robust and production-ready Django Ninja API, it is recommended to implement the following Celery use cases:

1. **Asynchronous Email Sending**

   - Offload password reset, account confirmation, and notification emails to Celery.
   - Improves API responsiveness and reliability (handles retries, avoids blocking requests).
   - This is a best practice for any production API.

2. **GDPR-Compliant User Data Export**

   - Implement a background task to gather and export all user data upon request.
   - Required for European users ("Right to Access"), and a good example of a long-running, user-triggered task.

3. **Scheduled Cleanups**
   - Use Celery periodic tasks (with django-celery-beat) to:
     - Remove images without a `polymorphic_image_relation`.
     - Remove tags (including polymorphic tags) that have no tag relations.
   - Keeps your data clean and minimizes storage costs.

**Rationale:**

- Implementing these covers the most common async/background needs for modern APIs.
- They serve as templates for future tasks and are easy to extend.
- Even simple tasks like sending emails benefit greatly from Celery (better UX, error handling, scalability).

You can stub or mock the more complex tasks initially, and fill in the full implementations as needed.
