import io
import json
import zipfile

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import User
from contacts.models import Contact
from images.models import Image, PolymorphicImageRelation
from organizations.export_archive import build_export_archive
from organizations.models import ExportJob, Membership, Organization
from tags.models import Tag, TaggedItem


@pytest.mark.django_db
def test_export_archive_contains_portable_data_and_media():
    user = User.objects.create_user(email="archive@example.com", password="pw")
    organization = Organization.objects.create(
        name="Archive",
        slug="archive-group",
        type="group",
        creator=user,
    )
    Membership.objects.create(
        user=user,
        organization=organization,
        role="owner",
    )
    contact = Contact.objects.create(
        organization=organization,
        creator=user,
        display_name="Ada Lovelace",
        slug="ada-lovelace",
    )
    tag = Tag.objects.create(
        organization=organization,
        name="VIP",
        slug="vip",
    )
    content_type = ContentType.objects.get_for_model(Contact)
    TaggedItem.objects.create(
        tag=tag,
        content_type=content_type,
        object_id=contact.pk,
    )
    image = Image.objects.create(
        organization=organization,
        creator=user,
        file=SimpleUploadedFile("portrait.jpg", b"image-bytes"),
    )
    PolymorphicImageRelation.objects.create(
        image=image,
        content_type=content_type,
        object_id=contact.pk,
        order=0,
        is_cover=True,
    )
    job = ExportJob.objects.create(organization=organization, requested_by=user)
    destination = io.BytesIO()

    build_export_archive(job, destination)

    destination.seek(0)
    with zipfile.ZipFile(destination) as archive:
        data = json.loads(archive.read("data.json"))
        media_name = f"media/{image.pk}/{image.file.name.rsplit('/', 1)[-1]}"
        assert archive.read(media_name) == b"image-bytes"

    assert data["format"] == "django-ninja-api-starter-portability-export"
    assert data["organization"]["id"] == organization.pk
    assert data["memberships"][0]["user_id"] == user.pk
    assert data["contacts"][0]["id"] == contact.pk
    assert data["tags"][0]["id"] == tag.pk
    assert data["tag_relations"][0]["object_id"] == contact.pk
    assert data["images"][0]["id"] == image.pk
    assert data["image_relations"][0]["image_id"] == image.pk
