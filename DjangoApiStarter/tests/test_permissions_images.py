from django.test import TestCase
from types import SimpleNamespace
from ninja.errors import HttpError
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from images.api import (
    list_images_for_org,
    list_images_for_object,
    bulk_upload_images,
    bulk_attach_images,
    attach_images,
    remove_image_from_object,
    edit_image_metadata,
    delete_image,
    bulk_delete_images,
)
from images.api import BulkImageIdsIn, ImageIdsIn
from images.schemas import ImagePatchIn
from images.models import Image, PolymorphicImageRelation
from django.contrib.contenttypes.models import ContentType
from organizations.models import Organization
from contacts.models import Contact


class TestImagePermissions(TestCase):
    def setUp(self):
        User = get_user_model()
        # Two users
        self.member = User.objects.create_user(email="member@example.com", password="pass12345")
        self.nonmember = User.objects.create_user(email="nonmember@example.com", password="pass12345")
        # Two orgs
        self.org = Organization.objects.create(name="Acme", slug="acme", creator=self.member)
        self.other_org = Organization.objects.create(name="Beta", slug="beta", creator=self.nonmember)
        # Make member belong to org (creator already counts as member through memberships)
        # Target object for attach
        self.contact = Contact.objects.create(display_name="John", slug="john", organization=self.org, creator=self.member)

    def _req(self, user, method="GET", path="/api/v1/"):
        return SimpleNamespace(user=user, headers={}, META={}, method=method, path=path, FILES=SimpleNamespace(getlist=lambda name: []))

    def test_non_member_cannot_list_images_for_org(self):
        req = self._req(self.nonmember, method="GET", path=f"/api/v1/images/orgs/{self.org.slug}/images/")
        with self.assertRaises(HttpError) as ctx:
            # Bypass @paginate decorator
            list_images_for_org.__wrapped__(req, self.org.slug, None)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_bulk_upload(self):
        req = self._req(self.nonmember, method="POST", path=f"/api/v1/images/orgs/{self.org.slug}/bulk-upload/")
        # Provide dummy files list to satisfy attribute access if reached (it shouldn't)
        files = [SimpleUploadedFile("a.jpg", b"x", content_type="image/jpeg")]
        req.FILES = SimpleNamespace(getlist=lambda name: files)
        with self.assertRaises(HttpError) as ctx:
            bulk_upload_images(req, self.org.slug)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_bulk_attach_rejects_cross_org_image_ids(self):
        # Member of self.org tries to attach an image from other_org
        cross_image = Image.objects.create(file="i/x.jpg", organization=self.other_org, creator=self.nonmember)
        data = BulkImageIdsIn(image_ids=[cross_image.id])
        req = self._req(self.member, method="POST", path=f"/api/v1/images/orgs/{self.org.slug}/images/contacts/contact/{self.contact.id}/bulk_attach/")
        with self.assertRaises(HttpError) as ctx:
            bulk_attach_images(req, self.org.slug, "contacts", "contact", self.contact.id, data)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_list_images_for_object(self):
        req = self._req(self.nonmember, method="GET", path=f"/api/v1/images/orgs/{self.org.slug}/images/contacts/contact/{self.contact.id}/")
        with self.assertRaises(HttpError) as ctx:
            # Bypass @paginate decorator
            list_images_for_object.__wrapped__(req, self.org.slug, "contacts", "contact", self.contact.id, None)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_list_images_for_object_wrong_org_slug(self):
        # Object belongs to self.org but we pass other_org slug -> 403
        req = self._req(self.member, method="GET", path=f"/api/v1/images/orgs/{self.other_org.slug}/images/contacts/contact/{self.contact.id}/")
        with self.assertRaises(HttpError) as ctx:
            list_images_for_object.__wrapped__(req, self.other_org.slug, "contacts", "contact", self.contact.id, None)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_attach_images(self):
        img = Image.objects.create(file="i/a.jpg", organization=self.org, creator=self.member)
        req = self._req(self.nonmember, method="POST", path=f"/api/v1/images/orgs/{self.org.slug}/images/contacts/contact/{self.contact.id}/")
        data = ImageIdsIn(image_ids=[img.id])
        with self.assertRaises(HttpError) as ctx:
            attach_images(req, self.org.slug, "contacts", "contact", self.contact.id, data)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_remove_image_from_object(self):
        img = Image.objects.create(file="i/b.jpg", organization=self.org, creator=self.member)
        # create relation
        PolymorphicImageRelation.objects.create(
            image=img,
            content_type=ContentType.objects.get_for_model(Contact),
            object_id=self.contact.id,
        )
        req = self._req(self.nonmember, method="DELETE", path=f"/api/v1/images/orgs/{self.org.slug}/images/contacts/contact/{self.contact.id}/{img.id}/")
        with self.assertRaises(HttpError) as ctx:
            remove_image_from_object(req, self.org.slug, "contacts", "contact", self.contact.id, img.id)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_edit_image_metadata(self):
        img = Image.objects.create(file="i/c.jpg", organization=self.org, creator=self.member)
        req = self._req(self.nonmember, method="PATCH", path=f"/api/v1/images/orgs/{self.org.slug}/images/{img.id}/")
        data = ImagePatchIn(title="New Title")
        with self.assertRaises(HttpError) as ctx:
            edit_image_metadata(req, self.org.slug, img.id, data)
        self.assertEqual(getattr(ctx.exception, "status_code", ""), 403)

    def test_non_member_cannot_delete_image(self):
        img = Image.objects.create(file="i/d.jpg", organization=self.org, creator=self.member)
        req = self._req(self.nonmember, method="DELETE", path=f"/api/v1/images/orgs/{self.org.slug}/images/{img.id}/")
        with self.assertRaises(HttpError) as ctx:
            delete_image(req, self.org.slug, img.id)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_bulk_delete(self):
        img = Image.objects.create(file="i/e.jpg", organization=self.org, creator=self.member)
        req = self._req(self.nonmember, method="POST", path=f"/api/v1/images/orgs/{self.org.slug}/bulk-delete/")
        # Provide JSON body to be parsed by endpoint
        import json as _json
        req.POST = None
        req.body = _json.dumps({"ids": [img.id]}).encode("utf-8")
        with self.assertRaises(HttpError) as ctx:
            bulk_delete_images(req, self.org.slug)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)
