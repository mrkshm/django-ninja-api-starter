from django.test import TestCase
from types import SimpleNamespace
from ninja.errors import HttpError
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from contacts.api import (
    get_contact,
    update_contact,
    partial_update_contact,
    delete_contact,
    upload_contact_avatar,
    delete_contact_avatar,
    create_contact,
)
from contacts.schemas import ContactIn
from contacts.models import Contact
from organizations.models import Organization


class TestContactPermissions(TestCase):
    def setUp(self):
        User = get_user_model()
        self.member = User.objects.create_user(email="member@example.com", password="pass12345")
        self.nonmember = User.objects.create_user(email="nonmember@example.com", password="pass12345")
        self.org = Organization.objects.create(name="Acme", slug="acme", creator=self.member)
        self.other_org = Organization.objects.create(name="Beta", slug="beta", creator=self.nonmember)
        self.contact = Contact.objects.create(display_name="John", slug="john", organization=self.org, creator=self.member)

    def _req(self, user, method="GET", path="/api/v1/"):
        # Minimal request stub
        return SimpleNamespace(user=user, headers={}, META={}, method=method, path=path, FILES={}, POST={})

    def test_non_member_cannot_get_contact(self):
        req = self._req(self.nonmember)
        with self.assertRaises(HttpError) as ctx:
            get_contact(req, self.contact.slug)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_update_contact(self):
        req = self._req(self.nonmember, method="PUT")
        data = ContactIn(
            display_name="Johnny",
            first_name="John",
            last_name="Doe",
            organization=self.org.slug,
            email="john@example.com",
            phone=None,
            address=None,
        )
        with self.assertRaises(HttpError) as ctx:
            update_contact(req, self.contact.slug, data)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_partial_update_contact(self):
        req = self._req(self.nonmember, method="PATCH")
        # Use ContactUpdate shape via partial schema dict
        from contacts.api import ContactUpdate
        patch = ContactUpdate(display_name="Johnny 2")
        with self.assertRaises(HttpError) as ctx:
            partial_update_contact(req, self.contact.slug, patch)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_delete_contact(self):
        req = self._req(self.nonmember, method="DELETE")
        with self.assertRaises(HttpError) as ctx:
            delete_contact(req, self.contact.slug)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_upload_avatar(self):
        req = self._req(self.nonmember, method="POST")
        # Fake image file
        file = SimpleUploadedFile("avatar.png", b"fakeimgbytes", content_type="image/png")
        with self.assertRaises(HttpError) as ctx:
            upload_contact_avatar(req, self.contact.slug, file)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_delete_avatar(self):
        req = self._req(self.nonmember, method="DELETE")
        with self.assertRaises(HttpError) as ctx:
            delete_contact_avatar(req, self.contact.slug)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)

    def test_non_member_cannot_create_contact_in_other_org(self):
        req = self._req(self.nonmember, method="POST")
        data = ContactIn(
            display_name="Betty",
            first_name="Betty",
            last_name="Beta",
            organization=self.org.slug,  # tries to create in org they don't belong to
            email="betty@example.com",
            phone=None,
            address=None,
        )
        with self.assertRaises(HttpError) as ctx:
            create_contact(req, data)
        self.assertEqual(getattr(ctx.exception, "status_code", 403), 403)
