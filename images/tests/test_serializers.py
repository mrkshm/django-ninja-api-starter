import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import default_storage

from contacts.models import Contact
from images.models import Image, PolymorphicImageRelation
from images.serializers import serialize_image, serialize_image_relation
from organizations.tests.utils import create_test_group


@pytest.mark.django_db
def test_serialize_image_adds_variant_keys_without_storage_checks(monkeypatch):
    def fail_exists(_name):
        raise AssertionError(
            "serialize_image must not perform storage existence checks"
        )

    monkeypatch.setattr(default_storage, "exists", fail_exists)

    User = get_user_model()
    user = User.objects.create_user(email="image-serializer@example.com", password="pw")
    org = create_test_group(name="Images", slug="images", owner=user)
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
    assert out.visibility == "private"
    assert out.url is None
    assert out.public_url is None
    assert out.variant_keys.original == "images/example.jpg"
    assert out.variant_keys.thumb == "images/example_thumb.webp"
    assert out.variant_keys.sm == "images/example_sm.webp"
    assert out.variant_keys.md == "images/example_md.webp"
    assert out.variant_keys.lg == "images/example_lg.webp"
    assert out.title == "Example"
    assert out.organization == org.id
    assert out.creator == user.id


@pytest.mark.django_db
def test_serialize_public_image_adds_public_urls(settings):
    settings.IMAGE_PUBLIC_BASE_URL = "https://media.example.com/assets/"

    User = get_user_model()
    user = User.objects.create_user(email="public-image@example.com", password="pw")
    org = create_test_group(name="Public Images", slug="public-images", owner=user)
    image = Image.objects.create(
        file="public/images/example image.jpg",
        organization=org,
        creator=user,
        visibility=Image.Visibility.PUBLIC,
    )

    out = serialize_image(image)

    assert out.visibility == "public"
    assert out.url is None
    assert (
        out.public_url
        == "https://media.example.com/assets/public/images/example%20image.jpg"
    )
    assert out.public_variant_urls.original == out.public_url
    assert (
        out.public_variant_urls.thumb
        == "https://media.example.com/assets/public/images/example%20image_thumb.webp"
    )
    assert out.variant_keys.thumb == "public/images/example image_thumb.webp"


@pytest.mark.django_db
def test_serialize_image_relation_adds_nested_image_and_relation_fields():
    User = get_user_model()
    user = User.objects.create_user(
        email="relation-serializer@example.com", password="pw"
    )
    org = create_test_group(name="Images", slug="images", owner=user)
    contact = Contact.objects.create(
        display_name="Jane", organization=org, creator=user
    )
    image = Image.objects.create(
        file="images/example.jpg", organization=org, creator=user
    )
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
