import pytest
from django.db.models.signals import pre_save

from accounts.models import User
from accounts.services import issue_token_pair
from images.models import Image
from organizations.models import Membership, Organization


def headers_for(user: User) -> dict[str, str]:
    access, _refresh = issue_token_pair(user)
    return {"Authorization": f"Bearer {access}"}


@pytest.fixture
def image_context():
    user = User.objects.create_user(email="metadata-owner@example.com", password="pw")
    organization = Organization.objects.create(
        name="Image Metadata", slug="image-metadata", type="group"
    )
    Membership.objects.create(user=user, organization=organization, role="owner")
    image = Image.objects.create(
        organization=organization,
        creator=user,
        file="private/images/metadata.webp",
        title="Original title",
        description="Original description",
        alt_text="Original alt text",
    )
    return user, organization, image


@pytest.mark.django_db
def test_metadata_patch_updates_only_submitted_fields(api_client, image_context):
    user, organization, image = image_context
    headers = headers_for(user)

    def concurrent_description_update(sender, instance, **kwargs):
        Image.objects.filter(pk=instance.pk).update(
            description="Concurrent description"
        )

    pre_save.connect(
        concurrent_description_update,
        sender=Image,
        dispatch_uid="test_metadata_partial_save",
    )
    try:
        response = api_client.patch(
            f"/orgs/{organization.slug}/images/{image.pk}/",
            json={"title": "Updated title"},
            headers=headers,
        )
    finally:
        pre_save.disconnect(
            sender=Image,
            dispatch_uid="test_metadata_partial_save",
        )

    assert response.status_code == 200
    image.refresh_from_db()
    assert image.title == "Updated title"
    assert image.description == "Concurrent description"
    assert image.alt_text == "Original alt text"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"title": None},
        {"description": None},
        {"alt_text": None},
        {"title": "x" * 121},
        {"alt_text": "x" * 121},
    ],
)
def test_metadata_patch_rejects_values_the_model_cannot_store(
    api_client,
    image_context,
    payload,
):
    user, organization, image = image_context

    response = api_client.patch(
        f"/orgs/{organization.slug}/images/{image.pk}/",
        json=payload,
        headers=headers_for(user),
    )

    assert response.status_code == 400
    image.refresh_from_db()
    assert image.title == "Original title"
    assert image.description == "Original description"
    assert image.alt_text == "Original alt text"
