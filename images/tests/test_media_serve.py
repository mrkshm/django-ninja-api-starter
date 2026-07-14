import io

import pytest
from django.http import Http404
from django.test import RequestFactory, override_settings

from images.views import media_serve


def test_media_serve_disabled_by_default():
    request = RequestFactory().get("/media/images/private.jpg")

    with pytest.raises(Http404):
        media_serve(request, "images/private.jpg")


@override_settings(ALLOW_UNAUTHENTICATED_MEDIA_SERVE=True)
def test_media_serve_can_be_enabled_for_local_proxy(monkeypatch):
    request = RequestFactory().get("/media/images/private.jpg")

    monkeypatch.setattr(
        "images.views.default_storage.open",
        lambda *args, **kwargs: io.BytesIO(b"image-bytes"),
    )

    response = media_serve(request, "images/private.jpg")

    assert response.status_code == 200
    assert response["Cache-Control"] == "private, max-age=300"
    assert b"".join(response.streaming_content) == b"image-bytes"
