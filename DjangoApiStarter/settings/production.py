from typing import Any, cast

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


def required(name: str) -> str:
    value = env.str(name, default="").strip()  # noqa: F405
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in production.")
    return value


DEBUG = False
SECRET_KEY = required("SECRET_KEY")
if SECRET_KEY in {
    "keySoS3cr3tOMGomgnoCaps",
    "django-insecure-development-only-secret-key",
}:
    raise ImproperlyConfigured("SECRET_KEY must be changed in production.")

JWT_SIGNING_KEY = required("JWT_SIGNING_KEY")
if JWT_SIGNING_KEY == SECRET_KEY:
    raise ImproperlyConfigured("JWT_SIGNING_KEY must be independent from SECRET_KEY.")
NINJA_JWT = {**NINJA_JWT, "SIGNING_KEY": JWT_SIGNING_KEY}  # noqa: F405

# Production emits one JSON object per application log record. Django has its
# own handler and does not propagate, preventing duplicate records at the root.
production_logging = cast(Any, LOGGING)  # noqa: F405
production_logging["root"]["handlers"] = ["console"]
production_logging["loggers"]["django"].update(
    {
        "handlers": ["console"],
        "propagate": False,
    }
)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")  # noqa: F405
FRONTEND_URL = required("FRONTEND_URL")
CORS_ALLOWED_ORIGINS = env.list(  # noqa: F405
    "CORS_ALLOWED_ORIGINS", default=[FRONTEND_URL]
)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405

DATABASES["default"].update(  # noqa: F405
    {
        "NAME": required("POSTGRES_DB"),
        "USER": required("POSTGRES_USER"),
        "PASSWORD": required("POSTGRES_PASSWORD"),
        "HOST": required("POSTGRES_HOST"),
    }
)

REDIS_URL = required("REDIS_URL")
CACHES["default"]["LOCATION"] = REDIS_URL  # noqa: F405
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

R2_ACCESS_KEY_ID = required("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = required("R2_SECRET_ACCESS_KEY")
R2_ENDPOINT_URL = required("R2_ENDPOINT_URL")
R2_PRIVATE_BUCKET_NAME = required("R2_PRIVATE_BUCKET_NAME")
R2_PUBLIC_BUCKET_NAME = required("R2_PUBLIC_BUCKET_NAME")
IMAGE_PUBLIC_BASE_URL = required("IMAGE_PUBLIC_BASE_URL")
cast(dict[str, Any], STORAGES["default"])["OPTIONS"].update(  # noqa: F405
    {
        "access_key": R2_ACCESS_KEY_ID,
        "secret_key": R2_SECRET_ACCESS_KEY,
        "bucket_name": R2_PRIVATE_BUCKET_NAME,
        "endpoint_url": R2_ENDPOINT_URL,
    }
)

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = required("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)  # noqa: F405
EMAIL_HOST_USER = required("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = required("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)  # noqa: F405
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)  # noqa: F405
DEFAULT_FROM_EMAIL = required("DEFAULT_FROM_EMAIL")
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ImproperlyConfigured(
        "EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled."
    )

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
