import io
import os
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image as PillowImage

from images.api.deletion import delete_image
from images.api.listing import list_images_for_org
from images.api.uploads import bulk_upload_images, upload_image
from images.models import Image
from organizations.models import Organization


class ScopeStub(SimpleNamespace):
    def require_write(self):
        return self


def unwrap_status(response):
    return response.status_code, response.value


def valid_image_file(name="image.png", image_format="PNG"):
    buffer = io.BytesIO()
    PillowImage.new("RGB", (32, 32), color="blue").save(buffer, format=image_format)
    return SimpleUploadedFile(
        name, buffer.getvalue(), content_type=f"image/{image_format.lower()}"
    )


@pytest.mark.django_db
class TestImageSuccessAndDeletion:
    def _req(self):
        return SimpleNamespace(
            auth=self.user,
            user=self.user,
            headers={},
            META={},
            FILES=SimpleNamespace(getlist=lambda name: []),
        )

    def setup_method(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="u@example.com", password="pass12345"
        )
        self.org = Organization.objects.create(
            name="Acme", slug="acme", creator=self.user
        )

    @override_settings(
        UPLOAD_IMAGE_MAX_BYTES=10 * 1024 * 1024,
        UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES=("image/",),
    )
    def test_single_upload_success_creates_image(self):
        req = self._req()
        f = valid_image_file("cat.png")
        with (
            patch(
                "images.api.uploads.resolve_org_scope",
                return_value=ScopeStub(org=self.org, user=self.user),
            ),
            patch("images.services.upload_to_storage") as mock_upload,
        ):
            resp = upload_image(req, self.org.slug, f)
            # Response is ImageOut model; assert it has id and file
            assert hasattr(resp, "id")
            assert resp.id
            assert Image.objects.filter(id=resp.id, organization=self.org).exists()
            assert resp.visibility == "private"
            mock_upload.assert_called()  # ensure storage called
            # Private-media responses expose storage keys, not public URLs.
            assert resp.url is None
            base = os.path.splitext(resp.file)[0]
            assert resp.variant_keys.original == resp.file
            assert resp.variant_keys.thumb == f"{base}_thumb.webp"
            assert resp.variant_keys.sm == f"{base}_sm.webp"
            assert resp.variant_keys.md == f"{base}_md.webp"
            assert resp.variant_keys.lg == f"{base}_lg.webp"

    @override_settings(
        UPLOAD_IMAGE_MAX_BYTES=10 * 1024 * 1024,
        UPLOAD_ALLOWED_IMAGE_MIME_PREFIXES=("image/",),
    )
    def test_bulk_upload_success(self):
        f1 = valid_image_file("a.jpg", "JPEG")
        f2 = valid_image_file("b.webp", "WEBP")
        files = [f1, f2]
        req = self._req()
        req.FILES = SimpleNamespace(getlist=lambda name: files)
        with (
            patch(
                "images.api.uploads.resolve_org_scope",
                return_value=ScopeStub(org=self.org, user=self.user),
            ),
            patch("images.services.upload_to_storage") as mock_upload,
        ):
            resp_list = bulk_upload_images(req, self.org.slug)
            assert len(resp_list) == 2
            assert all(r.status == "success" for r in resp_list)
            # Images created
            ids = [r.id for r in resp_list]
            assert Image.objects.filter(id__in=ids, organization=self.org).count() == 2
            assert mock_upload.call_count >= 2
            # Verify variant URLs through list endpoint
            list_req = self._req()
            # Call undecorated function to bypass @paginate wrapper
            with patch(
                "images.api.listing.resolve_org_scope",
                return_value=ScopeStub(org=self.org, user=self.user),
            ):
                images_out = list_images_for_org.__wrapped__(
                    list_req, self.org.slug, None
                )
            out_by_id = {img.id: img for img in images_out}
            for img_id in ids:
                img = out_by_id[img_id]
                assert img.url is None
                variants = img.variant_keys
                assert variants.original == img.file
                base = os.path.splitext(img.file)[0]
                assert variants.thumb == f"{base}_thumb.webp"
                assert variants.sm == f"{base}_sm.webp"
                assert variants.md == f"{base}_md.webp"
                assert variants.lg == f"{base}_lg.webp"

    def test_delete_removes_original_and_variants(
        self, django_capture_on_commit_callbacks
    ):
        # Create image with a known file name
        img = Image.objects.create(file="images/xyz.jpg", organization=self.org)
        req = self._req()
        with (
            patch(
                "images.api.deletion.resolve_org_scope",
                return_value=ScopeStub(org=self.org, user=self.user),
            ),
            patch("images.services.default_storage.delete") as mock_delete,
        ):
            with django_capture_on_commit_callbacks(execute=True):
                status, _ = unwrap_status(delete_image(req, self.org.slug, img.id))
            assert status == 204
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
            assert not Image.objects.filter(id=img.id).exists()
