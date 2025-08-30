from django.test import TestCase, override_settings
from unittest.mock import patch, call
from types import SimpleNamespace
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

from images.api import upload_image, bulk_upload_images, delete_image, list_images_for_org
import os
from images.models import Image
from organizations.models import Organization


class TestImageSuccessAndDeletion(TestCase):
    def _req(self):
        return SimpleNamespace(user=self.user, headers={}, META={}, FILES=SimpleNamespace(getlist=lambda name: []))

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="u@example.com", password="pass12345")
        self.org = Organization.objects.create(name="Acme", slug="acme", creator=self.user)

    @override_settings(UPLOAD_IMAGE_MAX_BYTES=10 * 1024 * 1024, UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES=("image/",))
    def test_single_upload_success_creates_image(self):
        req = self._req()
        f = SimpleUploadedFile("cat.png", b"\x89PNG\r\n\x1a\n" + b"x" * 100, content_type="image/png")
        with patch("images.api.get_org_for_request", return_value=self.org), \
             patch("images.api.upload_to_storage") as mock_upload, \
             patch("images.api.default_storage.url", side_effect=lambda p: f"/media/{p}"):
            resp = upload_image(req, self.org.slug, f)
            # Response is ImageOut model; assert it has id and file
            self.assertTrue(hasattr(resp, "id"))
            self.assertTrue(resp.id)
            self.assertTrue(Image.objects.filter(id=resp.id, organization=self.org).exists())
            mock_upload.assert_called()  # ensure storage called
            # Variant URLs assertions
            self.assertTrue(resp.url.startswith("/media/"))
            base = os.path.splitext(resp.file)[0]
            self.assertEqual(resp.variants.original, resp.url)
            # In tests, variant files are not actually present; backend now falls back to original
            self.assertEqual(resp.variants.thumb, resp.url)
            self.assertEqual(resp.variants.sm, resp.url)
            self.assertEqual(resp.variants.md, resp.url)
            self.assertEqual(resp.variants.lg, resp.url)

    @override_settings(UPLOAD_IMAGE_MAX_BYTES=10 * 1024 * 1024, UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES=("image/",))
    def test_bulk_upload_success(self):
        f1 = SimpleUploadedFile("a.jpg", b"JPEGDATA" * 10, content_type="image/jpeg")
        f2 = SimpleUploadedFile("b.webp", b"WEBPDATA" * 10, content_type="image/webp")
        files = [f1, f2]
        req = self._req()
        req.FILES = SimpleNamespace(getlist=lambda name: files)
        with patch("images.api.get_org_for_request", return_value=self.org), \
             patch("images.api.upload_to_storage") as mock_upload, \
             patch("images.api.default_storage.url", side_effect=lambda p: f"/media/{p}"):
            resp_list = bulk_upload_images(req, self.org.slug)
            self.assertEqual(len(resp_list), 2)
            self.assertTrue(all(r.status == "success" for r in resp_list))
            # Images created
            ids = [r.id for r in resp_list]
            self.assertEqual(Image.objects.filter(id__in=ids, organization=self.org).count(), 2)
            self.assertGreaterEqual(mock_upload.call_count, 2)
            # Verify variant URLs through list endpoint
            list_req = self._req()
            # Call undecorated function to bypass @paginate wrapper
            images_out = list_images_for_org.__wrapped__(list_req, self.org.slug, None)
            out_by_id = {img["id"]: img for img in images_out}
            for img_id in ids:
                img = out_by_id[img_id]
                assert img["url"].startswith("/media/")
                variants = img["variants"]
                # Fallback to original is expected in test environment (no variants written)
                assert variants["original"] == img["url"]
                assert variants["thumb"] == img["url"]
                assert variants["sm"] == img["url"]
                assert variants["md"] == img["url"]
                assert variants["lg"] == img["url"]

    def test_delete_removes_original_and_variants(self):
        # Create image with a known file name
        img = Image.objects.create(file="images/xyz.jpg", organization=self.org)
        req = self._req()
        with patch("images.api.get_org_for_request", return_value=self.org), \
             patch("images.api.default_storage.delete") as mock_delete:
            status, _ = delete_image(req, self.org.slug, img.id)
            self.assertEqual(status, 204)
            # Original + 4 variants
            base = "images/xyz"
            expected_calls = [
                call(f"{base}_thumb.webp"),
                call(f"{base}_sm.webp"),
                call(f"{base}_md.webp"),
                call(f"{base}_lg.webp"),
                call("images/xyz.jpg"),
            ]
            mock_delete.assert_has_calls(expected_calls, any_order=True)
            self.assertFalse(Image.objects.filter(id=img.id).exists())
