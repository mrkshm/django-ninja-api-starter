from django.test import TestCase, override_settings
from types import SimpleNamespace
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

from images.api import (
    bulk_upload_images,
    bulk_attach_images,
    bulk_detach_images,
    bulk_delete_images,
)
from images.api import BulkImageIdsIn
from images.models import Image
from organizations.models import Organization
from contacts.models import Contact


@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
})
class TestIdempotencyBulk(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="u@example.com", password="pass12345")
        self.org = Organization.objects.create(name="Acme", slug="acme", creator=self.user)
        self.contact = Contact.objects.create(display_name="John", slug="john", organization=self.org, creator=self.user)

    def _req(self, method: str, path: str, idem_key: str):
        # Minimal request stub with headers, META, method, path, user, FILES/POST/body
        return SimpleNamespace(
            user=self.user,
            headers={"Idempotency-Key": idem_key},
            META={"HTTP_IDEMPOTENCY_KEY": idem_key},
            method=method,
            path=path,
            FILES=SimpleNamespace(getlist=lambda name: []),
            POST=None,
            body=b"",
        )

    def test_bulk_upload_idempotent_same_key(self):
        files = [
            SimpleUploadedFile("a.jpg", b"JPEGDATA" * 5, content_type="image/jpeg"),
            SimpleUploadedFile("b.png", b"PNGDATA" * 5, content_type="image/png"),
        ]
        path = "/api/v1/images/orgs/acme/bulk-upload/"
        req1 = self._req("POST", path, "key-1")
        req1.FILES = SimpleNamespace(getlist=lambda name: files)
        req2 = self._req("POST", path, "key-1")
        req2.FILES = SimpleNamespace(getlist=lambda name: files)
        with patch("images.api.get_org_for_request", return_value=self.org), \
             patch("images.api.upload_to_storage") as mock_upload, \
             patch("images.api.default_storage.url", side_effect=lambda p: f"/media/{p}"):
            first = bulk_upload_images(req1, self.org.slug)
            second = bulk_upload_images(req2, self.org.slug)
            # First call returns list of schema objects; second returns cached list of dicts
            first_norm = [dict(id=r.id, file=r.file, status=r.status, error=r.error) for r in first]
            # second may be list[dict]
            second_norm = [dict(id=r.get("id"), file=r.get("file"), status=r.get("status"), error=r.get("error")) for r in second]
            self.assertEqual(first_norm, second_norm)
            # Storage should have been called only once for each file
            self.assertEqual(mock_upload.call_count, len(files))

    def test_bulk_upload_different_keys_trigger_fresh_run(self):
        files = [
            SimpleUploadedFile("a.jpg", b"JPEGDATA" * 5, content_type="image/jpeg"),
            SimpleUploadedFile("b.png", b"PNGDATA" * 5, content_type="image/png"),
        ]
        path = "/api/v1/images/orgs/acme/bulk-upload/"
        req1 = self._req("POST", path, "key-A")
        req1.FILES = SimpleNamespace(getlist=lambda name: files)
        req2 = self._req("POST", path, "key-B")
        req2.FILES = SimpleNamespace(getlist=lambda name: files)
        with patch("images.api.get_org_for_request", return_value=self.org), \
             patch("images.api.upload_to_storage") as mock_upload, \
             patch("images.api.default_storage.url", side_effect=lambda p: f"/media/{p}"):
            first = bulk_upload_images(req1, self.org.slug)
            second = bulk_upload_images(req2, self.org.slug)
            # Different keys should not hit cache, so storage called twice per file set
            self.assertEqual(mock_upload.call_count, len(files) * 2)
            # The created image ids should be distinct sets
            first_ids = {r.id for r in first}
            second_ids = {r.id for r in second}
            self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_bulk_attach_idempotent_same_key(self):
        # Prepare two images
        img1 = Image.objects.create(file="i/1.jpg", organization=self.org, creator=self.user)
        img2 = Image.objects.create(file="i/2.jpg", organization=self.org, creator=self.user)
        data = BulkImageIdsIn(image_ids=[img1.id, img2.id])
        path = f"/api/v1/images/orgs/{self.org.slug}/images/contacts/contact/{self.contact.id}/bulk_attach/"
        req1 = self._req("POST", path, "key-2")
        req2 = self._req("POST", path, "key-2")
        with patch("images.api.get_org_for_request", return_value=self.org):
            first = bulk_attach_images(req1, self.org.slug, "contacts", "contact", self.contact.id, data)
            second = bulk_attach_images(req2, self.org.slug, "contacts", "contact", self.contact.id, data)
            self.assertEqual(first, second)
            self.assertCountEqual(first["attached"], [img1.id, img2.id])

    def test_bulk_detach_idempotent_same_key(self):
        # Attach first
        img1 = Image.objects.create(file="i/1.jpg", organization=self.org, creator=self.user)
        img2 = Image.objects.create(file="i/2.jpg", organization=self.org, creator=self.user)
        attach_path = f"/api/v1/images/orgs/{self.org.slug}/images/contacts/contact/{self.contact.id}/bulk_attach/"
        req_attach = self._req("POST", attach_path, "key-3a")
        with patch("images.api.get_org_for_request", return_value=self.org):
            bulk_attach_images(req_attach, self.org.slug, "contacts", "contact", self.contact.id, BulkImageIdsIn(image_ids=[img1.id, img2.id]))
        # Now detach twice with same key
        detach_path = f"/api/v1/images/orgs/{self.org.slug}/images/contacts/contact/{self.contact.id}/bulk_detach/"
        req1 = self._req("POST", detach_path, "key-3b")
        req2 = self._req("POST", detach_path, "key-3b")
        with patch("images.api.get_org_for_request", return_value=self.org):
            first = bulk_detach_images(req1, self.org.slug, "contacts", "contact", self.contact.id, BulkImageIdsIn(image_ids=[img1.id, img2.id]))
            second = bulk_detach_images(req2, self.org.slug, "contacts", "contact", self.contact.id, BulkImageIdsIn(image_ids=[img1.id, img2.id]))
            self.assertEqual(first, second)
            self.assertCountEqual(first["detached"], [img1.id, img2.id])

    def test_bulk_delete_idempotent_same_key(self):
        img1 = Image.objects.create(file="i/1.jpg", organization=self.org, creator=self.user)
        img2 = Image.objects.create(file="i/2.jpg", organization=self.org, creator=self.user)
        path = f"/api/v1/images/orgs/{self.org.slug}/bulk-delete/"
        # Simulate JSON body
        import json
        body = json.dumps({"ids": [img1.id, img2.id]}).encode("utf-8")
        req1 = self._req("POST", path, "key-4")
        req1.body = body
        req2 = self._req("POST", path, "key-4")
        req2.body = body
        with patch("images.api.get_org_for_request", return_value=self.org):
            status1, _ = bulk_delete_images(req1, self.org.slug)
            status2, _ = bulk_delete_images(req2, self.org.slug)
            self.assertEqual(status1, 204)
            self.assertEqual(status2, 204)
            self.assertEqual(Image.objects.filter(id__in=[img1.id, img2.id]).count(), 0)
