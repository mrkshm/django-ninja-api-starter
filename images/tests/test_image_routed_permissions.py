import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image as PillowImage

from accounts.models import User
from accounts.services import issue_token_pair
from contacts.models import Contact
from images.models import Image
from organizations.models import Membership, Organization
from organizations.tests.utils import create_test_group


def headers_for(user: User) -> dict[str, str]:
    access, _refresh = issue_token_pair(user)
    return {"Authorization": f"Bearer {access}"}


def image_file() -> SimpleUploadedFile:
    buffer = io.BytesIO()
    PillowImage.new("RGB", (16, 16), color="blue").save(buffer, format="PNG")
    return SimpleUploadedFile("image.png", buffer.getvalue(), content_type="image/png")


@pytest.mark.django_db
def test_outsider_cannot_use_any_image_read_or_mutation_route(api_client):
    owner = User.objects.create_user(email="image-owner@example.com", password="pw")
    outsider = User.objects.create_user(
        email="image-outsider@example.com", password="pw"
    )
    organization = Organization.objects.create(
        name="Image Permissions", slug="image-permissions", type="group"
    )
    Membership.objects.create(user=owner, organization=organization, role="owner")
    contact = Contact.objects.create(
        display_name="Image Target",
        slug="image-target",
        organization=organization,
        creator=owner,
    )
    image = Image.objects.create(
        organization=organization,
        creator=owner,
        file="private/images/protected.webp",
    )
    headers = headers_for(outsider)
    org_base = f"/orgs/{organization.slug}"
    object_base = f"{org_base}/images/contacts/contact/{contact.pk}"

    responses = [
        api_client.get(f"{org_base}/images/", headers=headers),
        api_client.get(f"{object_base}/", headers=headers),
        api_client.post(
            f"{org_base}/bulk-upload/",
            data={},
            FILES={"files": [image_file()]},
            headers=headers,
        ),
        api_client.post(
            f"{object_base}/",
            json={"image_ids": [image.pk]},
            headers=headers,
        ),
        api_client.post(
            f"{object_base}/bulk_attach/",
            json={"image_ids": [image.pk]},
            headers=headers,
        ),
        api_client.post(
            f"{object_base}/bulk_detach/",
            json={"image_ids": [image.pk]},
            headers=headers,
        ),
        api_client.delete(f"{object_base}/{image.pk}/", headers=headers),
        api_client.patch(
            f"{org_base}/images/{image.pk}/",
            json={"title": "Forbidden"},
            headers=headers,
        ),
        api_client.delete(f"{org_base}/images/{image.pk}/", headers=headers),
        api_client.post(
            f"{org_base}/bulk-delete/",
            json={"ids": [image.pk]},
            headers=headers,
        ),
    ]

    assert [(response.status_code, response.json()) for response in responses] == [
        (404, {"detail": "Organization not found"})
    ] * len(responses)
    image.refresh_from_db()
    assert image.title == ""


@pytest.mark.django_db
def test_object_routes_hide_targets_from_another_organization(api_client):
    user = User.objects.create_user(email="image-scope@example.com", password="pw")
    visible_org = Organization.objects.create(
        name="Visible Images", slug="visible-images", type="group"
    )
    hidden_org = create_test_group(name="Hidden Images", slug="hidden-images")
    Membership.objects.create(user=user, organization=visible_org, role="owner")
    hidden_contact = Contact.objects.create(
        display_name="Hidden Target",
        slug="hidden-target",
        organization=hidden_org,
        creator=user,
    )
    path = f"/orgs/{visible_org.slug}/images/contacts/contact/{hidden_contact.pk}/"

    response = api_client.get(path, headers=headers_for(user))

    assert response.status_code == 404
    assert response.json() == {"detail": "Object not found"}
