from django.test import TestCase, override_settings
from types import SimpleNamespace
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from images.api import upload_image, bulk_upload_images


class TestImageUploadValidations(TestCase):
    def _req(self):
        # Minimal request stub with user and headers/FILES
        return SimpleNamespace(user=SimpleNamespace(id=1), headers={}, META={}, FILES=SimpleNamespace(getlist=lambda name: []))

    @override_settings(UPLOAD_IMAGE_MAX_BYTES=5)  # very small to trigger
    def test_single_upload_rejects_oversize(self):
        req = self._req()
        tiny_limit = 5
        content = b"x" * (tiny_limit + 1)
        f = SimpleUploadedFile("test.png", content, content_type="image/png")
        with patch("images.api.get_org_for_request", return_value=SimpleNamespace(slug="acme")):
            status, body = upload_image(req, "acme", f)
            self.assertEqual(status, 400)
            self.assertIn("File too large", body["detail"]) 

    @override_settings(UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES=("image/",))
    def test_single_upload_rejects_bad_mime(self):
        req = self._req()
        f = SimpleUploadedFile("doc.pdf", b"%PDF-1.4", content_type="application/pdf")
        with patch("images.api.get_org_for_request", return_value=SimpleNamespace(slug="acme")):
            status, body = upload_image(req, "acme", f)
            self.assertEqual(status, 400)
            self.assertIn("Invalid file type", body["detail"]) 

    @override_settings(UPLOAD_IMAGE_MAX_BYTES=6)
    def test_bulk_upload_marks_oversize_as_error(self):
        # Create two files: one oversize (>6 bytes), one small but invalid MIME (<=6 bytes)
        oversize = SimpleUploadedFile("big.jpg", b"x" * 7, content_type="image/jpeg")
        bad_mime = SimpleUploadedFile("doc.pdf", b"abcd", content_type="application/pdf")
        files = [oversize, bad_mime]
        req = self._req()
        req.FILES = SimpleNamespace(getlist=lambda name: files)
        with patch("images.api.get_org_for_request", return_value=SimpleNamespace(slug="acme")):
            # Expect responses array with error entries, no exceptions
            resp_list = bulk_upload_images(req, "acme")
            self.assertEqual(len(resp_list), 2)
            self.assertTrue(all(r.status == "error" for r in resp_list))
            errors = [r.error for r in resp_list]
            self.assertIn("File too large", errors[0])
            self.assertIn("Invalid file type", errors[1])
