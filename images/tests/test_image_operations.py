import pytest
from django.contrib.contenttypes.models import ContentType
from django.db.models.query import QuerySet

from accounts.models import User
from contacts.models import Contact
from images.models import Image, PolymorphicImageRelation
from images.operations import attach_images_to_object
from organizations.models import Organization


@pytest.mark.django_db
def test_attach_operation_locks_existing_relations(monkeypatch):
    user = User.objects.create_user(email="image-lock@example.com", password="pw")
    organization = Organization.objects.create(
        name="Image Lock", slug="image-lock", type="group"
    )
    contact = Contact.objects.create(
        display_name="Lock Target",
        organization=organization,
        creator=user,
    )
    image = Image.objects.create(
        file="private/images/lock.webp",
        organization=organization,
        creator=user,
    )
    content_type = ContentType.objects.get_for_model(contact)
    locked_relation_models = []
    original_select_for_update = QuerySet.select_for_update

    def tracking_select_for_update(self, *args, **kwargs):
        if self.model is PolymorphicImageRelation:
            locked_relation_models.append(self.model)
        return original_select_for_update(self, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "select_for_update", tracking_select_for_update)

    result = attach_images_to_object(
        organization_id=organization.pk,
        target=contact,
        content_type=content_type,
        image_ids=[image.pk],
    )

    assert result.attached_image_ids == [image.pk]
    assert locked_relation_models == [PolymorphicImageRelation]
