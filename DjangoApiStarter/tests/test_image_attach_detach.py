from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from contacts.models import Contact
from images.api import (
    BulkImageIdsIn,
    ImageIdsIn,
    attach_images,
    bulk_attach_images,
    bulk_detach_images,
    list_images_for_object,
    remove_image_from_object,
)
from images.models import Image, PolymorphicImageRelation
from organizations.models import Membership, Organization


def unwrap_status(response):
    return response.status_code, response.value


@pytest.mark.django_db
class TestImageAttachDetach:
    def _req(self):
        return SimpleNamespace(auth=self.user, user=self.user, headers={}, META={})

    def setup_method(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345"
        )
        self.org = Organization.objects.create(
            name="Acme", slug="acme", creator=self.user
        )
        Membership.objects.create(user=self.user, organization=self.org, role="owner")
        # Target object to attach images to
        self.contact = Contact.objects.create(
            display_name="John Doe",
            slug="john-doe",
            organization=self.org,
            creator=self.user,
        )
        # Two images in the same org
        self.img1 = Image.objects.create(
            file="images/one.jpg", organization=self.org, creator=self.user
        )
        self.img2 = Image.objects.create(
            file="images/two.jpg", organization=self.org, creator=self.user
        )

    def test_single_attach_and_remove(self):
        req = self._req()
        # Single attach via attach_images (uses ImageIdsIn)
        out = attach_images(
            req,
            self.org.slug,
            "contacts",
            "contact",
            self.contact.id,
            ImageIdsIn(image_ids=[self.img1.id]),
        )
        assert len(out) == 1
        assert PolymorphicImageRelation.objects.filter(
            image_id=self.img1.id, object_id=self.contact.id
        ).exists()
        # Remove via remove_image_from_object
        status, _ = unwrap_status(
            remove_image_from_object(
                req, self.org.slug, "contacts", "contact", self.contact.id, self.img1.id
            )
        )
        assert status == 204
        assert not PolymorphicImageRelation.objects.filter(
            image_id=self.img1.id, object_id=self.contact.id
        ).exists()

    def test_single_attach_locks_existing_relations(self, monkeypatch):
        from django.db.models.query import QuerySet

        calls = []
        original_select_for_update = QuerySet.select_for_update

        def tracking_select_for_update(self, *args, **kwargs):
            if self.model is PolymorphicImageRelation:
                calls.append(self.model)
            return original_select_for_update(self, *args, **kwargs)

        monkeypatch.setattr(QuerySet, "select_for_update", tracking_select_for_update)

        attach_images(
            self._req(),
            self.org.slug,
            "contacts",
            "contact",
            self.contact.id,
            ImageIdsIn(image_ids=[self.img1.id]),
        )

        assert calls == [PolymorphicImageRelation]

    def test_bulk_attach_and_detach(self):
        req = self._req()
        # Bulk attach
        resp = bulk_attach_images(
            req,
            self.org.slug,
            "contacts",
            "contact",
            self.contact.id,
            BulkImageIdsIn(image_ids=[self.img1.id, self.img2.id]),
        )
        assert sorted(resp["attached"]) == sorted([self.img1.id, self.img2.id])
        assert (
            PolymorphicImageRelation.objects.filter(object_id=self.contact.id).count()
            == 2
        )
        # Bulk detach
        resp2 = bulk_detach_images(
            req,
            self.org.slug,
            "contacts",
            "contact",
            self.contact.id,
            BulkImageIdsIn(image_ids=[self.img1.id, self.img2.id]),
        )
        assert sorted(resp2["detached"]) == sorted([self.img1.id, self.img2.id])
        assert (
            PolymorphicImageRelation.objects.filter(object_id=self.contact.id).count()
            == 0
        )
