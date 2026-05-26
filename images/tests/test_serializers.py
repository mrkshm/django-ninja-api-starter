import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import default_storage

from contacts.models import Contact
from images.models import Image, PolymorphicImageRelation
from images.serializers import serialize_image, serialize_image_relation
from organizations.models import Organization


@pytest.mark.django_db
def test_serialize_image_adds_stable_media_urls(monkeypatch):
    def fail_exists(_name):
        raise AssertionError("serialize_image must not perform storage existence checks")

    monkeypatch.setattr(default_storage, "exists", fail_exists)

    User = get_user_model()
    user = User.objects.create_user(email="image-serializer@example.com", password="pw")
    org = Organization.objects.create(name="Images", slug="images", type="group")
    image = Image.objects.create(
        file="images/example.jpg",
        organization=org,
        creator=user,
        title="Example",
        description="Description",
        alt_text="Alt",
    )

    out = serialize_image(image)

    assert out.id == image.id
    assert out.file == "images/example.jpg"
    assert out.url == "/media/images/example.jpg"
    assert out.variants.original == out.url
    assert out.variants.thumb == "/media/images/example_thumb.webp"
    assert out.variants.sm == "/media/images/example_sm.webp"
    assert out.variants.md == "/media/images/example_md.webp"
    assert out.variants.lg == "/media/images/example_lg.webp"
    assert out.title == "Example"
    assert out.organization == org.id
    assert out.creator == user.id


@pytest.mark.django_db
def test_serialize_image_relation_adds_nested_image_and_relation_fields():
    User = get_user_model()
    user = User.objects.create_user(email="relation-serializer@example.com", password="pw")
    org = Organization.objects.create(name="Images", slug="images", type="group")
    contact = Contact.objects.create(display_name="Jane", organization=org, creator=user)
    image = Image.objects.create(file="images/example.jpg", organization=org, creator=user)
    content_type = ContentType.objects.get_for_model(contact)
    relation = PolymorphicImageRelation.objects.create(
        image=image,
        content_type=content_type,
        object_id=contact.id,
        is_cover=True,
        order=2,
        custom_title="Relation title",
    )

    out = serialize_image_relation(relation)

    assert out.id == relation.id
    assert out.image.id == image.id
    assert out.content_type == "contact"
    assert out.object_id == contact.id
    assert out.is_cover is True
    assert out.order == 2
    assert out.custom_title == "Relation title"
