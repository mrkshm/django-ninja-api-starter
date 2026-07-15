from pathlib import Path
from datetime import timedelta

import environ

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

PROJECT_NAME = env.str("PROJECT_NAME", default="DjangoApiStarter")
FRONTEND_URL = env.str("FRONTEND_URL", default="http://localhost:3000")

SECRET_KEY = env.str(
    "SECRET_KEY",
    default="django-insecure-development-only-secret-key",
)
DEBUG = False

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"],
)

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[FRONTEND_URL],
)
CORS_ALLOW_CREDENTIALS = False
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": ("'self'", "https://cdn.jsdelivr.net"),
        "style-src": ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"),
        "img-src": ("'self'", "data:", "blob:", "https://django-ninja.dev"),
        "font-src": ("'self'",),
        "connect-src": ("'self'",),
        "frame-ancestors": ("'none'",),
    }
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja_extra",
    "csp",
    "corsheaders",
    "django_celery_beat",
    "ninja_jwt.token_blacklist",
    "accounts.apps.AccountsConfig",
    "organizations.apps.OrganizationsConfig",
    "core",
    "contacts.apps.ContactsConfig",
    "tags",
    "images",
]

MIDDLEWARE = [
    "DjangoApiStarter.middleware.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
]

AUTH_USER_MODEL = "accounts.User"
ROOT_URLCONF = "DjangoApiStarter.urls"
WSGI_APPLICATION = "DjangoApiStarter.wsgi.application"
ASGI_APPLICATION = "DjangoApiStarter.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.str("POSTGRES_DB", default="django_db"),
        "USER": env.str("POSTGRES_USER", default="django_user"),
        "PASSWORD": env.str("POSTGRES_PASSWORD", default="django_pass"),
        "HOST": env.str("POSTGRES_HOST", default="db"),
        "PORT": env.int("POSTGRES_PORT", default=5432),
        "CONN_MAX_AGE": env.int("POSTGRES_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
    }
}

REDIS_URL = env.str("REDIS_URL", default="redis://redis:6379/1")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=25 * 60)
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=30 * 60)
CELERY_RESULT_EXPIRES = env.int("CELERY_RESULT_EXPIRES", default=60 * 60)
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ROUTES = {
    "core.tasks.send_email_task": {"queue": "email"},
    "organizations.export_tasks.export_org_data_task": {"queue": "exports"},
    "organizations.export_tasks.cleanup_expired_exports": {"queue": "maintenance"},
    "accounts.tasks.cleanup_expired_tokens": {"queue": "maintenance"},
}

CELERY_BEAT_SCHEDULE = {
    "cleanup_expired_tokens": {
        "task": "accounts.tasks.cleanup_expired_tokens",
        "schedule": 24 * 60 * 60,
    },
    "cleanup_expired_exports": {
        "task": "organizations.export_tasks.cleanup_expired_exports",
        "schedule": 24 * 60 * 60,
    },
}

R2_ACCESS_KEY_ID = env.str("R2_ACCESS_KEY_ID", default="")
R2_SECRET_ACCESS_KEY = env.str("R2_SECRET_ACCESS_KEY", default="")
R2_ENDPOINT_URL = env.str("R2_ENDPOINT_URL", default="http://localhost:9000")
R2_REGION_NAME = env.str("R2_REGION_NAME", default="auto")
R2_PRIVATE_BUCKET_NAME = env.str(
    "R2_PRIVATE_BUCKET_NAME",
    default=env.str("R2_BUCKET_NAME", default="private-media"),
)
R2_PUBLIC_BUCKET_NAME = env.str("R2_PUBLIC_BUCKET_NAME", default="")

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "access_key": R2_ACCESS_KEY_ID,
            "secret_key": R2_SECRET_ACCESS_KEY,
            "bucket_name": R2_PRIVATE_BUCKET_NAME,
            "endpoint_url": R2_ENDPOINT_URL,
            "region_name": R2_REGION_NAME,
            "addressing_style": "virtual",
            "signature_version": "s3v4",
            "default_acl": None,
            "querystring_auth": True,
        },
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

IMAGE_PUBLIC_BASE_URL = env.str("IMAGE_PUBLIC_BASE_URL", default="") or None
IMAGE_SIGNED_URL_TTL_SECONDS = env.int("IMAGE_SIGNED_URL_TTL_SECONDS", default=15 * 60)
IMAGE_SHARE_LINK_DEFAULT_TTL_SECONDS = env.int(
    "IMAGE_SHARE_LINK_DEFAULT_TTL_SECONDS",
    default=7 * 24 * 60 * 60,
)
UPLOAD_IMAGE_MAX_BYTES = env.int("UPLOAD_IMAGE_MAX_BYTES", default=10 * 1024 * 1024)
UPLOAD_IMAGE_MAX_PIXELS = env.int("UPLOAD_IMAGE_MAX_PIXELS", default=40_000_000)
UPLOAD_IMAGE_MAX_DIMENSION = env.int("UPLOAD_IMAGE_MAX_DIMENSION", default=12_000)
EXPORT_RETENTION_DAYS = env.int("EXPORT_RETENTION_DAYS", default=7)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="webmaster@localhost")
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN = env.bool(
    "REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN",
    default=True,
)

JWT_SIGNING_KEY = env.str(
    "JWT_SIGNING_KEY",
    default="development-only-jwt-signing-key-change-me",
)
NINJA_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": JWT_SIGNING_KEY,
    "AUDIENCE": env.str("JWT_AUDIENCE", default="django-ninja-api"),
    "ISSUER": env.str("JWT_ISSUER", default="django-ninja-api"),
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ALLOW_UNAUTHENTICATED_MEDIA_SERVE = False
UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES = tuple(
    prefix.strip()
    for prefix in env.str("UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES", default="image/").split(
        ","
    )
    if prefix.strip()
)

NINJA_RATELIMIT_ENABLE = env.bool("NINJA_RATELIMIT_ENABLE", default=True)
IMAGES_RATE_LIMIT_UPLOAD = env.str("IMAGES_RATE_LIMIT_UPLOAD", default="60/h")
IMAGES_RATE_LIMIT_BULK_UPLOAD = env.str("IMAGES_RATE_LIMIT_BULK_UPLOAD", default="30/h")
IMAGES_RATE_LIMIT_BULK_DELETE = env.str("IMAGES_RATE_LIMIT_BULK_DELETE", default="30/h")
IMAGES_RATE_LIMIT_BULK_ATTACH = env.str("IMAGES_RATE_LIMIT_BULK_ATTACH", default="60/h")
IMAGES_RATE_LIMIT_BULK_DETACH = env.str("IMAGES_RATE_LIMIT_BULK_DETACH", default="60/h")
IMAGES_RATE_LIMIT_SHARE_RESOLVE = env.str(
    "IMAGES_RATE_LIMIT_SHARE_RESOLVE", default="120/h"
)

LOG_LEVEL = env.str("LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "core.utils.logging.JSONFormatter"},
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": LOG_LEVEL,
            "stream": "ext://sys.stdout",
            "formatter": "json",
        },
        "console_plain": {
            "class": "logging.StreamHandler",
            "level": LOG_LEVEL,
            "stream": "ext://sys.stdout",
            "formatter": "plain",
        },
    },
    "loggers": {
        "audit": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django": {
            "handlers": ["console_plain"],
            "level": LOG_LEVEL,
            "propagate": True,
        },
    },
    "root": {"handlers": ["console_plain"], "level": LOG_LEVEL},
}
