from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from ninja.errors import HttpError

from contacts.models import Contact
from images.api.deletion import bulk_delete_images, delete_image
from images.api.listing import list_images_for_object, list_images_for_org
from images.api.metadata import edit_image_metadata
from images.api.relations import (
    attach_images,
    bulk_attach_images,
    remove_image_from_object,
)
from images.api.uploads import bulk_upload_images
from images.api_schemas import BulkImageIdsIn, ImageIdsIn
from images.models import Image, PolymorphicImageRelation
from images.schemas import ImagePatchIn
from organizations.models import Organization


@pytest.mark.django_db
class TestImagePermissions:
    def setup_method(self):
        User = get_user_model()
        # Two users
        self.member = User.objects.create_user(
            email="member@example.com", password="pass12345"
        )
        self.nonmember = User.objects.create_user(
            email="nonmember@example.com", password="pass12345"
        )
        # Two orgs
        self.org = Organization.objects.create(
            name="Acme", slug="acme", creator=self.member
        )
        self.other_org = Organization.objects.create(
            name="Beta", slug="beta", creator=self.nonmember
        )
        # Make member belong to org (creator already counts as member through memberships)
        # Target object for attach
        self.contact = Contact.objects.create(
            display_name="John", slug="john", organization=self.org, creator=self.member
        )

    def _req(self, user, method="GET", path="/api/v1/"):
        return SimpleNamespace(
            auth=user,
            user=user,
            headers={},
            META={},
            method=method,
            path=path,
            FILES=SimpleNamespace(getlist=lambda name: []),
        )

    def test_non_member_cannot_list_images_for_org(self):
        req = self._req(
            self.nonmember, method="GET", path=f"/api/v1/orgs/{self.org.slug}/images/"
        )
        with pytest.raises(HttpError) as ctx:
            # Bypass @paginate decorator
            list_images_for_org.__wrapped__(req, self.org.slug, None)
        assert getattr(ctx.value, "status_code", 404) == 404

    def test_non_member_cannot_bulk_upload(self):
        req = self._req(
            self.nonmember,
            method="POST",
            path=f"/api/v1/orgs/{self.org.slug}/bulk-upload/",
        )
        # Provide dummy files list to satisfy attribute access if reached (it shouldn't)
        files = [SimpleUploadedFile("a.jpg", b"x", content_type="image/jpeg")]
        req.FILES = SimpleNamespace(getlist=lambda name: files)
        with pytest.raises(HttpError) as ctx:
            bulk_upload_images(req, self.org.slug)
        assert getattr(ctx.value, "status_code", 404) == 404

    def test_bulk_attach_rejects_cross_org_image_ids(self):
        # Member of self.org tries to attach an image from other_org
        cross_image = Image.objects.create(
            file="i/x.jpg", organization=self.other_org, creator=self.nonmember
        )
        data = BulkImageIdsIn(image_ids=[cross_image.id])
        req = self._req(
            self.member,
            method="POST",
            path=f"/api/v1/orgs/{self.org.slug}/images/contacts/contact/{self.contact.id}/bulk_attach/",
        )
        with pytest.raises(HttpError) as ctx:
            bulk_attach_images(
                req, self.org.slug, "contacts", "contact", self.contact.id, data
            )
        assert getattr(ctx.value, "status_code", 404) == 404

    def test_non_member_cannot_list_images_for_object(self):
        req = self._req(
            self.nonmember,
            method="GET",
            path=f"/api/v1/orgs/{self.org.slug}/images/contacts/contact/{self.contact.id}/",
        )
        with pytest.raises(HttpError) as ctx:
            # Bypass @paginate decorator
            list_images_for_object.__wrapped__(
                req, self.org.slug, "contacts", "contact", self.contact.id, None
            )
        assert getattr(ctx.value, "status_code", 404) == 404

    def test_list_images_for_object_wrong_org_slug(self):
        # Object belongs to self.org but we pass other_org slug -> 404
        req = self._req(
            self.member,
            method="GET",
            path=f"/api/v1/orgs/{self.other_org.slug}/images/contacts/contact/{self.contact.id}/",
        )
        with pytest.raises(HttpError) as ctx:
            list_images_for_object.__wrapped__(
                req, self.other_org.slug, "contacts", "contact", self.contact.id, None
            )
        assert getattr(ctx.value, "status_code", 404) == 404

    def test_non_member_cannot_attach_images(self):
        img = Image.objects.create(
            file="i/a.jpg", organization=self.org, creator=self.member
        )
        req = self._req(
            self.nonmember,
            method="POST",
            path=f"/api/v1/orgs/{self.org.slug}/images/contacts/contact/{self.contact.id}/",
        )
        data = ImageIdsIn(image_ids=[img.id])
        with pytest.raises(HttpError) as ctx:
            attach_images(
                req, self.org.slug, "contacts", "contact", self.contact.id, data
            )
        assert getattr(ctx.value, "status_code", 404) == 404

    def test_non_member_cannot_remove_image_from_object(self):
        img = Image.objects.create(
            file="i/b.jpg", organization=self.org, creator=self.member
        )
        # create relation
        PolymorphicImageRelation.objects.create(
            image=img,
            content_type=ContentType.objects.get_for_model(Contact),
            object_id=self.contact.id,
        )
        req = self._req(
            self.nonmember,
            method="DELETE",
            path=f"/api/v1/orgs/{self.org.slug}/images/contacts/contact/{self.contact.id}/{img.id}/",
        )
        with pytest.raises(HttpError) as ctx:
            remove_image_from_object(
                req, self.org.slug, "contacts", "contact", self.contact.id, img.id
            )
        assert getattr(ctx.value, "status_code", 404) == 404

    def test_non_member_cannot_edit_image_metadata(self):
        img = Image.objects.create(
            file="i/c.jpg", organization=self.org, creator=self.member
        )
        req = self._req(
            self.nonmember,
            method="PATCH",
            path=f"/api/v1/orgs/{self.org.slug}/images/{img.id}/",
        )
        data = ImagePatchIn(title="New Title")
        with pytest.raises(HttpError) as ctx:
            edit_image_metadata(req, self.org.slug, img.id, data)
        assert getattr(ctx.value, "status_code", "") == 404

    def test_non_member_cannot_delete_image(self):
        img = Image.objects.create(
            file="i/d.jpg", organization=self.org, creator=self.member
        )
        req = self._req(
            self.nonmember,
            method="DELETE",
            path=f"/api/v1/orgs/{self.org.slug}/images/{img.id}/",
        )
        with pytest.raises(HttpError) as ctx:
            delete_image(req, self.org.slug, img.id)
        assert getattr(ctx.value, "status_code", 404) == 404

    def test_non_member_cannot_bulk_delete(self):
        img = Image.objects.create(
            file="i/e.jpg", organization=self.org, creator=self.member
        )
        req = self._req(
            self.nonmember,
            method="POST",
            path=f"/api/v1/orgs/{self.org.slug}/bulk-delete/",
        )
        # Provide JSON body to be parsed by endpoint
        import json as _json

        req.POST = None
        req.body = _json.dumps({"ids": [img.id]}).encode("utf-8")
        with pytest.raises(HttpError) as ctx:
            bulk_delete_images(req, self.org.slug)
        assert getattr(ctx.value, "status_code", 404) == 404
