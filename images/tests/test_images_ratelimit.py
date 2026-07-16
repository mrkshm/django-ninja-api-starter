import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image as PilImage

from organizations.models import Membership, Organization

User = get_user_model()


def create_test_image_file(color=(50, 50, 200), size=(100, 100), name="t.png"):
    img = PilImage.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")


def get_access_token(email, password):
    client = Client()
    resp = client.post(
        "/api/v1/token/pair",
        data={"email": email, "password": password},
        content_type="application/json",
    )
    if resp.status_code != 200:
        # Fallback to form
        resp = client.post(
            "/api/v1/token/pair",
            data={"email": email, "password": password},
            content_type="application/x-www-form-urlencoded",
        )
    return resp.json().get("access")


def _enable_test_throttling(instance_names, monkeypatch):
    """Override throttle instances to test route-level 429 handling."""
    from images import throttles

    for name in instance_names:
        thr = getattr(throttles, name)
        # track per-instance call count for this test process
        monkeypatch.setattr(thr, "_test_calls", 0, raising=False)

        def _allow_once(
            self, request, *args, **kwargs
        ):  # signature compatible with both forms
            calls = getattr(self, "_test_calls", 0)
            setattr(self, "_test_calls", calls + 1)
            # allow first call, deny second and subsequent
            return calls == 0

        # bind to instance
        monkeypatch.setattr(thr, "allow_request", _allow_once.__get__(thr, object))

        # ensure wait() exists and does not rely on internal state
        def _wait(self):
            return 60  # seconds until next permitted request

        monkeypatch.setattr(thr, "wait", _wait.__get__(thr, object))
        # add a history attribute to satisfy any checks
        if not hasattr(thr, "history"):
            monkeypatch.setattr(thr, "history", [], raising=False)


@pytest.mark.django_db
def test_single_upload_rate_limited(monkeypatch):
    org = Organization.objects.create(name="RLOrg", slug="rlorg")
    user = User.objects.create_user(
        email="rl@example.com", password="pw", email_verified=True
    )
    Membership.objects.create(user=user, organization=org, role="owner")

    # Enable throttling for single upload: allow once then 429
    _enable_test_throttling(["upload_throttle"], monkeypatch)

    client = Client()
    access = get_access_token("rl@example.com", "pw")
    assert access

    url = f"/api/v1/orgs/{org.slug}/images/"
    file1 = create_test_image_file(name="a.png")
    r1 = client.post(url, {"file": file1}, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert r1.status_code == 200, r1.content

    file2 = create_test_image_file(name="b.png")
    r2 = client.post(url, {"file": file2}, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert r2.status_code == 429, r2.content


@pytest.mark.django_db
def test_bulk_upload_rate_limited(monkeypatch):
    org = Organization.objects.create(name="RLBulkOrg", slug="rlbulkog")
    user = User.objects.create_user(
        email="rlbulk@example.com", password="pw", email_verified=True
    )
    Membership.objects.create(user=user, organization=org, role="owner")

    # Enable throttling for bulk upload: allow once then 429
    _enable_test_throttling(["bulk_upload_throttle"], monkeypatch)

    client = Client()
    access = get_access_token("rlbulk@example.com", "pw")
    assert access

    url = f"/api/v1/orgs/{org.slug}/bulk-upload/"
    files1 = {"files": [create_test_image_file(name="c1.png")]}
    r1 = client.post(url, files1, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert r1.status_code == 200, r1.content

    files2 = {"files": [create_test_image_file(name="c2.png")]}
    r2 = client.post(url, files2, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert r2.status_code == 429, r2.content
