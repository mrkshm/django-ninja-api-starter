from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from ninja.errors import HttpError

from images.api import bulk_upload_images, upload_image


class ScopeStub(SimpleNamespace):
    def require_write(self):
        return self


@pytest.mark.django_db
class TestImageUploadValidations:
    def _req(self):
        # Minimal request stub with user and headers/FILES
        user = SimpleNamespace(id=1, is_authenticated=True)
        return SimpleNamespace(
            auth=user,
            user=user,
            headers={},
            META={},
            FILES=SimpleNamespace(getlist=lambda name: []),
        )

    @override_settings(UPLOAD_IMAGE_MAX_BYTES=5)  # very small to trigger
    def test_single_upload_rejects_oversize(self):
        req = self._req()
        tiny_limit = 5
        content = b"x" * (tiny_limit + 1)
        f = SimpleUploadedFile("test.png", content, content_type="image/png")
        with patch(
            "images.api.uploads.resolve_org_scope",
            return_value=ScopeStub(org=SimpleNamespace(slug="acme"), user=req.auth),
        ):
            with pytest.raises(HttpError) as exc:
                upload_image(req, "acme", f)
        assert exc.value.status_code == 400
        assert "File too large" in exc.value.message

    @override_settings(UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES=("image/",))
    def test_single_upload_rejects_bad_mime(self):
        req = self._req()
        f = SimpleUploadedFile("doc.pdf", b"%PDF-1.4", content_type="application/pdf")
        with patch(
            "images.api.uploads.resolve_org_scope",
            return_value=ScopeStub(org=SimpleNamespace(slug="acme"), user=req.auth),
        ):
            with pytest.raises(HttpError) as exc:
                upload_image(req, "acme", f)
        assert exc.value.status_code == 400
        assert "Invalid file type" in exc.value.message

    @override_settings(UPLOAD_IMAGE_MAX_BYTES=6)
    def test_bulk_upload_rejects_oversize_before_processing(self):
        # One file is oversized; the other is small but has an invalid MIME type.
        oversize = SimpleUploadedFile("big.jpg", b"x" * 7, content_type="image/jpeg")
        bad_mime = SimpleUploadedFile(
            "doc.pdf", b"abcd", content_type="application/pdf"
        )
        files = [oversize, bad_mime]
        req = self._req()
        req.FILES = SimpleNamespace(getlist=lambda name: files)
        with patch(
            "images.api.uploads.resolve_org_scope",
            return_value=ScopeStub(org=SimpleNamespace(slug="acme"), user=req.auth),
        ):
            with pytest.raises(HttpError) as exc:
                bulk_upload_images(req, "acme")
        assert exc.value.status_code == 400
        assert "per-file size" in exc.value.message

    @override_settings(UPLOAD_IMAGE_MAX_FILES_PER_REQUEST=1)
    def test_bulk_upload_rejects_excessive_file_count(self):
        files = [
            SimpleUploadedFile("a.jpg", b"a", content_type="image/jpeg"),
            SimpleUploadedFile("b.jpg", b"b", content_type="image/jpeg"),
        ]
        req = self._req()
        req.FILES = SimpleNamespace(getlist=lambda name: files)
        with patch(
            "images.api.uploads.resolve_org_scope",
            return_value=ScopeStub(org=SimpleNamespace(slug="acme"), user=req.auth),
        ):
            with pytest.raises(HttpError) as exc:
                bulk_upload_images(req, "acme")
        assert exc.value.status_code == 400
        assert "at most 1" in exc.value.message

    @override_settings(UPLOAD_IMAGE_MAX_TOTAL_BYTES=5)
    def test_bulk_upload_rejects_declared_aggregate_size(self):
        files = [
            SimpleUploadedFile("a.jpg", b"aaa", content_type="image/jpeg"),
            SimpleUploadedFile("b.jpg", b"bbb", content_type="image/jpeg"),
        ]
        req = self._req()
        req.FILES = SimpleNamespace(getlist=lambda name: files)
        with patch(
            "images.api.uploads.resolve_org_scope",
            return_value=ScopeStub(org=SimpleNamespace(slug="acme"), user=req.auth),
        ):
            with pytest.raises(HttpError) as exc:
                bulk_upload_images(req, "acme")
        assert exc.value.status_code == 400
        assert "aggregate size" in exc.value.message
