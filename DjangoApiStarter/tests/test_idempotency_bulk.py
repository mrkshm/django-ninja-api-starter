from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from ninja.errors import HttpError

from contacts.models import Contact
from images.api import (
    BulkImageIdsIn,
    bulk_attach_images,
    bulk_delete_images,
    bulk_detach_images,
    bulk_upload_images,
)
from images.models import Image
from organizations.models import Membership, Organization


class ScopeStub(SimpleNamespace):
    def require_write(self):
        return self


def unwrap_status(response):
    return response.status_code, response.value


@pytest.mark.django_db
class TestIdempotencyBulk:
    def setup_method(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="u@example.com", password="pass12345"
        )
        self.org = Organization.objects.create(
            name="Acme", slug="acme", creator=self.user
        )
        Membership.objects.create(user=self.user, organization=self.org, role="owner")
        self.contact = Contact.objects.create(
            display_name="John", slug="john", organization=self.org, creator=self.user
        )

    def _req(self, method: str, path: str, idem_key: str):
        # Minimal request stub with headers, META, method, path, user, FILES/POST/body
        return SimpleNamespace(
            auth=self.user,
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
        path = "/api/v1/orgs/acme/bulk-upload/"
        req1 = self._req("POST", path, "key-1")
        req1.FILES = SimpleNamespace(getlist=lambda name: files)
        req2 = self._req("POST", path, "key-1")
        req2.FILES = SimpleNamespace(getlist=lambda name: files)

        def fake_upload(data, organization, original_name, creator_id=None):
            return Image.objects.create(
                file=f"private/images/{original_name}",
                organization=organization,
                creator_id=creator_id,
            )

        with (
            patch(
                "images.api.uploads.resolve_org_scope",
                return_value=ScopeStub(org=self.org, user=self.user),
            ),
            patch(
                "images.api.uploads.upload_image_file", side_effect=fake_upload
            ) as mock_upload,
        ):
            first = bulk_upload_images(req1, self.org.slug)
            cache.clear()
            second = bulk_upload_images(req2, self.org.slug)
            assert [item.model_dump() for item in first] == [
                item.model_dump() for item in second
            ]
            # Storage should have been called only once for each file
            assert mock_upload.call_count == len(files)

    def test_bulk_upload_different_keys_trigger_fresh_run(self):
        files = [
            SimpleUploadedFile("a.jpg", b"JPEGDATA" * 5, content_type="image/jpeg"),
            SimpleUploadedFile("b.png", b"PNGDATA" * 5, content_type="image/png"),
        ]
        path = "/api/v1/orgs/acme/bulk-upload/"
        req1 = self._req("POST", path, "key-A")
        req1.FILES = SimpleNamespace(getlist=lambda name: files)
        req2 = self._req("POST", path, "key-B")
        req2.FILES = SimpleNamespace(getlist=lambda name: files)

        def fake_upload(data, organization, original_name, creator_id=None):
            return Image.objects.create(
                file=f"private/images/{original_name}",
                organization=organization,
                creator_id=creator_id,
            )

        with (
            patch(
                "images.api.uploads.resolve_org_scope",
                return_value=ScopeStub(org=self.org, user=self.user),
            ),
            patch(
                "images.api.uploads.upload_image_file", side_effect=fake_upload
            ) as mock_upload,
        ):
            first = bulk_upload_images(req1, self.org.slug)
            second = bulk_upload_images(req2, self.org.slug)
            # Different keys should not hit cache, so storage called twice per file set
            assert mock_upload.call_count == len(files * 2)
            # The created image ids should be distinct sets
            first_ids = {r.id for r in first}
            second_ids = {r.id for r in second}
            assert first_ids.isdisjoint(second_ids)

    def test_bulk_upload_same_metadata_different_bytes_conflicts(self):
        first_files = [SimpleUploadedFile("a.jpg", b"AAAA", content_type="image/jpeg")]
        changed_files = [
            SimpleUploadedFile("a.jpg", b"BBBB", content_type="image/jpeg")
        ]
        path = "/api/v1/orgs/acme/bulk-upload/"
        req1 = self._req("POST", path, "content-key")
        req1.FILES = SimpleNamespace(getlist=lambda name: first_files)
        req2 = self._req("POST", path, "content-key")
        req2.FILES = SimpleNamespace(getlist=lambda name: changed_files)

        def fake_upload(data, organization, original_name, creator_id=None):
            return Image.objects.create(
                file=f"private/images/{original_name}",
                organization=organization,
                creator_id=creator_id,
            )

        with (
            patch(
                "images.api.uploads.resolve_org_scope",
                return_value=ScopeStub(org=self.org, user=self.user),
            ),
            patch("images.api.uploads.upload_image_file", side_effect=fake_upload),
        ):
            bulk_upload_images(req1, self.org.slug)
            with pytest.raises(HttpError) as conflict:
                bulk_upload_images(req2, self.org.slug)

        assert conflict.value.status_code == 409

    def test_bulk_attach_idempotent_same_key(self):
        # Prepare two images
        img1 = Image.objects.create(
            file="i/1.jpg", organization=self.org, creator=self.user
        )
        img2 = Image.objects.create(
            file="i/2.jpg", organization=self.org, creator=self.user
        )
        data = BulkImageIdsIn(image_ids=[img1.id, img2.id])
        path = (
            f"/api/v1/orgs/{self.org.slug}/images/contacts/contact/"
            f"{self.contact.id}/bulk_attach/"
        )
        req1 = self._req("POST", path, "key-2")
        req2 = self._req("POST", path, "key-2")
        first = bulk_attach_images(
            req1, self.org.slug, "contacts", "contact", self.contact.id, data
        )
        second = bulk_attach_images(
            req2, self.org.slug, "contacts", "contact", self.contact.id, data
        )
        assert first == second
        assert sorted(first["attached"]) == sorted([img1.id, img2.id])

    def test_bulk_detach_idempotent_same_key(self):
        # Attach first
        img1 = Image.objects.create(
            file="i/1.jpg", organization=self.org, creator=self.user
        )
        img2 = Image.objects.create(
            file="i/2.jpg", organization=self.org, creator=self.user
        )
        attach_path = (
            f"/api/v1/orgs/{self.org.slug}/images/contacts/contact/"
            f"{self.contact.id}/bulk_attach/"
        )
        req_attach = self._req("POST", attach_path, "key-3a")
        bulk_attach_images(
            req_attach,
            self.org.slug,
            "contacts",
            "contact",
            self.contact.id,
            BulkImageIdsIn(image_ids=[img1.id, img2.id]),
        )
        # Now detach twice with same key
        detach_path = (
            f"/api/v1/orgs/{self.org.slug}/images/contacts/contact/"
            f"{self.contact.id}/bulk_detach/"
        )
        req1 = self._req("POST", detach_path, "key-3b")
        req2 = self._req("POST", detach_path, "key-3b")
        first = bulk_detach_images(
            req1,
            self.org.slug,
            "contacts",
            "contact",
            self.contact.id,
            BulkImageIdsIn(image_ids=[img1.id, img2.id]),
        )
        second = bulk_detach_images(
            req2,
            self.org.slug,
            "contacts",
            "contact",
            self.contact.id,
            BulkImageIdsIn(image_ids=[img1.id, img2.id]),
        )
        assert first == second
        assert sorted(first["detached"]) == sorted([img1.id, img2.id])

    def test_bulk_delete_idempotent_same_key(self):
        img1 = Image.objects.create(
            file="i/1.jpg", organization=self.org, creator=self.user
        )
        img2 = Image.objects.create(
            file="i/2.jpg", organization=self.org, creator=self.user
        )
        path = f"/api/v1/orgs/{self.org.slug}/bulk-delete/"
        # Simulate JSON body
        import json

        body = json.dumps({"ids": [img1.id, img2.id]}).encode("utf-8")
        req1 = self._req("POST", path, "key-4")
        req1.body = body
        req2 = self._req("POST", path, "key-4")
        req2.body = body
        with patch(
            "images.api.deletion.resolve_org_scope",
            return_value=ScopeStub(org=self.org, user=self.user),
        ):
            status1, _ = unwrap_status(bulk_delete_images(req1, self.org.slug))
            status2, _ = unwrap_status(bulk_delete_images(req2, self.org.slug))
            assert status1 == 204
            assert status2 == 204
            assert Image.objects.filter(id__in=[img1.id, img2.id]).count() == 0

    def test_bulk_delete_idempotent_partial_failure(self):
        img = Image.objects.create(
            file="i/1.jpg", organization=self.org, creator=self.user
        )
        missing_id = img.id + 999
        path = f"/api/v1/orgs/{self.org.slug}/bulk-delete/"
        import json

        body = json.dumps({"ids": [img.id, missing_id]}).encode("utf-8")
        req1 = self._req("POST", path, "key-5")
        req1.body = body
        req2 = self._req("POST", path, "key-5")
        req2.body = body

        with patch(
            "images.api.deletion.resolve_org_scope",
            return_value=ScopeStub(org=self.org, user=self.user),
        ):
            status1, body1 = unwrap_status(bulk_delete_images(req1, self.org.slug))
            status2, body2 = unwrap_status(bulk_delete_images(req2, self.org.slug))

        assert status1 == 400
        assert status2 == 400
        assert body1 == body2
        assert body1["deleted"] == [img.id]
        assert body1["failed"] == [{"id": missing_id, "reason": "not found"}]
        assert not Image.objects.filter(id=img.id).exists()
