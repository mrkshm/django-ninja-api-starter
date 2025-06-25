from django.test import TestCase
from types import SimpleNamespace
from django.contrib.auth import get_user_model

from images.api import (
    attach_images,
    bulk_attach_images,
    bulk_detach_images,
    remove_image_from_object,
    list_images_for_object,
    ImageIdsIn,
    BulkImageIdsIn,
)
from images.models import Image, PolymorphicImageRelation
from organizations.models import Organization
from contacts.models import Contact
from unittest.mock import patch


class TestImageAttachDetach(TestCase):
    def _req(self):
        return SimpleNamespace(user=self.user, headers={}, META={})

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="owner@example.com", password="pass12345")
        self.org = Organization.objects.create(name="Acme", slug="acme", creator=self.user)
        # Target object to attach images to
        self.contact = Contact.objects.create(display_name="John Doe", slug="john-doe", organization=self.org, creator=self.user)
        # Two images in the same org
        self.img1 = Image.objects.create(file="images/one.jpg", organization=self.org, creator=self.user)
        self.img2 = Image.objects.create(file="images/two.jpg", organization=self.org, creator=self.user)

    def test_single_attach_and_remove(self):
        req = self._req()
        with patch("images.api.get_org_for_request", return_value=self.org):
            # Single attach via attach_images (uses ImageIdsIn)
            out = attach_images(req, self.org.slug, "contacts", "contact", self.contact.id, ImageIdsIn(image_ids=[self.img1.id]))
            self.assertEqual(len(out), 1)
            self.assertTrue(PolymorphicImageRelation.objects.filter(image_id=self.img1.id, object_id=self.contact.id).exists())
            # Remove via remove_image_from_object
            status, _ = remove_image_from_object(req, self.org.slug, "contacts", "contact", self.contact.id, self.img1.id)
            self.assertEqual(status, 204)
            self.assertFalse(PolymorphicImageRelation.objects.filter(image_id=self.img1.id, object_id=self.contact.id).exists())

    def test_bulk_attach_and_detach(self):
        req = self._req()
        with patch("images.api.get_org_for_request", return_value=self.org):
            # Bulk attach
            resp = bulk_attach_images(req, self.org.slug, "contacts", "contact", self.contact.id, BulkImageIdsIn(image_ids=[self.img1.id, self.img2.id]))
            self.assertCountEqual(resp["attached"], [self.img1.id, self.img2.id])
            self.assertEqual(PolymorphicImageRelation.objects.filter(object_id=self.contact.id).count(), 2)
            # Bulk detach
            resp2 = bulk_detach_images(req, self.org.slug, "contacts", "contact", self.contact.id, BulkImageIdsIn(image_ids=[self.img1.id, self.img2.id]))
            self.assertCountEqual(resp2["detached"], [self.img1.id, self.img2.id])
            self.assertEqual(PolymorphicImageRelation.objects.filter(object_id=self.contact.id).count(), 0)
