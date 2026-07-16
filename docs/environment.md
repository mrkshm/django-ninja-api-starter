# Environment variables

`env.example` documents development values and `env.production.example` is the
production template. Production rejects missing mandatory values.

| Area | Variables |
| --- | --- |
| Django | `PROJECT_NAME`, `SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `BROWSER_REFRESH_COOKIE_SECURE` (local development only) |
| JWT | `JWT_SIGNING_KEY`, `JWT_AUDIENCE`, `JWT_ISSUER` |
| PostgreSQL | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_CONN_MAX_AGE` |
| Redis/Celery | `REDIS_URL`, `REDIS_PASSWORD` (Compose), `CELERY_TASK_SOFT_TIME_LIMIT`, `CELERY_TASK_TIME_LIMIT`, `EXPORT_STALE_AFTER_SECONDS`, `EXPORT_RECOVERY_INTERVAL_SECONDS` |
| Private storage | `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL`, `R2_REGION_NAME`, `R2_PRIVATE_BUCKET_NAME` |
| Public avatars | `R2_PUBLIC_BUCKET_NAME`, `IMAGE_PUBLIC_BASE_URL` |
| Email | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL` |
| HTTP/runtime | `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `NINJA_NUM_PROXIES`, `WEB_CONCURRENCY`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`, `GUNICORN_GRACEFUL_TIMEOUT`, `LOG_LEVEL` |
| Upload limits | `UPLOAD_IMAGE_MAX_BYTES`, `UPLOAD_IMAGE_MAX_FILES_PER_REQUEST`, `UPLOAD_IMAGE_MAX_TOTAL_BYTES` |
| Retention | `EXPORT_RETENTION_DAYS` and image/share limit variables in `settings/base.py` |
| Compose only | `APP_IMAGE`, `APP_ENV_FILE`, `DOMAIN` |

Generate secrets with a cryptographically secure generator. Do not commit the
real environment file or pass secrets as Docker build arguments. Restrict the
file to the deployment account (`chmod 600`) and prefer a secrets manager when
the deployment platform provides one.

Browser auth assumes an exact, same-site frontend origin. Production and staging
should each set `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, and
`CSRF_TRUSTED_ORIGINS` to their own frontend, such as `https://app.example.com`
or `https://app-staging.example.com`. Production forces the refresh cookie to
`Secure`; `BROWSER_REFRESH_COOKIE_SECURE=False` exists only so local HTTP
development works.

`EXPORT_STALE_AFTER_SECONDS` must exceed `CELERY_TASK_TIME_LIMIT`; its default is
five minutes longer. Beat scans at `EXPORT_RECOVERY_INTERVAL_SECONDS` and
requeues jobs whose queue/worker activity has stopped.

`NINJA_NUM_PROXIES=1` matches the supported deployment where Caddy is the sole
public proxy. If a CDN or another trusted proxy is added, configure Caddy's
trusted proxy ranges and update this count to the number of trusted hops between
the client and Django. A wrong count makes IP-based throttle buckets unreliable.

Image uploads default to 10 MiB per file, 20 files per bulk request, and 50 MiB
of aggregate input. The application enforces both declared and streamed sizes;
proxy-level request limits should provide an additional outer bound.
