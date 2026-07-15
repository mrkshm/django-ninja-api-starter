from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = "test-only-secret-key-that-is-long-enough-for-hs256"
NINJA_JWT = {
    **NINJA_JWT,  # noqa: F405
    "SIGNING_KEY": "test-only-jwt-signing-key-that-is-long-enough-for-hs256",
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "django-ninja-api-starter-tests",
    }
}

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {
            "location": BASE_DIR / ".test_media",  # noqa: F405
            "base_url": "/media/",
        },
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_BROKER_URL = "memory://"
REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN = False
