from .base import *  # noqa: F403

DEBUG = True

CORS_ALLOWED_ORIGINS = [
    FRONTEND_URL,  # noqa: F405
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

STORAGES = {  # noqa: F405
    **STORAGES,  # noqa: F405
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
