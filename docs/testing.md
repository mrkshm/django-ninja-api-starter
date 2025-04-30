# Testing Guide

This document explains how to run tests safely and efficiently in this project, especially with regard to file storage backends.

## Why Not Use S3 in Tests?

By default, this project uses S3-compatible storage in production. Running tests against S3 can be slow, expensive, and may risk deleting or modifying production data. To avoid this, all tests override the storage backend to use the local filesystem (FileSystemStorage) instead.

## How Storage is Overridden in Tests

In any test that deals with file uploads or deletions, the storage backend is set to local using the `settings` fixture:

```python
settings.STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
```

This ensures:

- All file uploads and deletions use the local filesystem, never S3 or remote storage.
- Tests are fast, safe, and isolated from production data.

## Customizing Test Settings

You can add further test-only overrides in your test code or fixtures, such as:

- Faster password hashers
- Dummy email backend
- Different cache settings

Example:

```python
settings.PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
```

## Continuous Integration (CI)

Make sure your CI pipeline also uses the same pattern to override storage in tests.

## Troubleshooting

- If you see errors about S3 or remote storage during tests, double-check you are overriding the storage backend in your test code or fixtures.
- If you add new test-only requirements, add them to your test code and document them here.

---

For any questions or improvements, see the project maintainers or open an issue.
