import os
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1].parent


def _import_settings_with_env(extra_env):
    env = os.environ.copy()
    env.update(
        {
            "R2_ACCESS_KEY_ID": "test-access-key",
            "R2_SECRET_ACCESS_KEY": "test-secret-key",
            "R2_ENDPOINT_URL": "http://localhost:9000",
            "R2_BUCKET_NAME": "test-private-bucket",
            "R2_PRIVATE_BUCKET_NAME": "test-private-bucket",
            "R2_PUBLIC_BUCKET_NAME": "test-public-bucket",
        }
    )
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", "import DjangoApiStarter.settings"],
        cwd=BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_production_rejects_insecure_default_secret_key():
    result = _import_settings_with_env(
        {
            "DEBUG": "False",
            "SECRET_KEY": "keySoS3cr3tOMGomgnoCaps",
        }
    )

    assert result.returncode != 0
    assert "SECRET_KEY must be changed in production" in result.stderr


def test_production_accepts_explicit_secret_key():
    result = _import_settings_with_env(
        {
            "DEBUG": "False",
            "SECRET_KEY": "not-the-default-secret-key",
        }
    )

    assert result.returncode == 0, result.stderr


def test_docker_compose_does_not_define_secret_key_default():
    compose = (BASE_DIR / "docker-compose.yml").read_text()

    assert "keySoS3cr3tOMGomgnoCaps" not in compose
    assert "SECRET_KEY: ${SECRET_KEY}" in compose


def test_allauth_is_not_configured_when_jwt_auth_is_used(settings):
    assert "allauth" not in settings.INSTALLED_APPS
    assert "allauth.account" not in settings.INSTALLED_APPS
    assert "allauth.socialaccount" not in settings.INSTALLED_APPS
    assert "allauth.account.middleware.AccountMiddleware" not in settings.MIDDLEWARE


def test_unused_third_party_apps_are_not_configured(settings):
    assert "django.contrib.sites" not in settings.INSTALLED_APPS
    assert "django_filters" not in settings.INSTALLED_APPS
    assert "health_check" not in settings.INSTALLED_APPS
    assert "defender" not in settings.INSTALLED_APPS
    assert "imagekit" not in settings.INSTALLED_APPS
