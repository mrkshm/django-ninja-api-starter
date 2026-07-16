import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image as PillowImage

from accounts.models import User
from accounts.services import issue_token_pair
from contacts.models import Contact
from organizations.models import Membership, Organization


def headers_for(user: User) -> dict[str, str]:
    access, _refresh = issue_token_pair(user)
    return {"Authorization": f"Bearer {access}"}


def avatar_file() -> SimpleUploadedFile:
    buffer = io.BytesIO()
    PillowImage.new("RGB", (16, 16), color="blue").save(buffer, format="PNG")
    return SimpleUploadedFile("avatar.png", buffer.getvalue(), content_type="image/png")


@pytest.mark.django_db
def test_outsider_cannot_use_any_contact_read_or_mutation_route(api_client):
    owner = User.objects.create_user(email="contact-owner@example.com", password="pw")
    outsider = User.objects.create_user(
        email="contact-outsider@example.com", password="pw"
    )
    organization = Organization.objects.create(
        name="Contact Permissions", slug="contact-permissions", type="group"
    )
    Membership.objects.create(user=owner, organization=organization, role="owner")
    contact = Contact.objects.create(
        display_name="Protected Contact",
        slug="protected-contact",
        organization=organization,
        creator=owner,
        avatar_path="public/avatars/contacts/protected.webp",
    )
    headers = headers_for(outsider)
    collection = f"/orgs/{organization.slug}/contacts/"
    detail = f"{collection}{contact.slug}/"

    responses = [
        api_client.get(detail, headers=headers),
        api_client.post(
            collection,
            json={"display_name": "Forbidden Create"},
            headers=headers,
        ),
        api_client.put(
            detail,
            json={"display_name": "Forbidden Replace"},
            headers=headers,
        ),
        api_client.patch(
            detail,
            json={"display_name": "Forbidden Patch"},
            headers=headers,
        ),
        api_client.post(
            f"{detail}avatar/",
            data={},
            FILES={"file": avatar_file()},
            headers=headers,
        ),
        api_client.delete(f"{detail}avatar/", headers=headers),
        api_client.delete(detail, headers=headers),
    ]

    assert [(response.status_code, response.json()) for response in responses] == [
        (404, {"detail": "Organization not found"})
    ] * len(responses)
    assert Contact.objects.filter(pk=contact.pk).exists()
    contact.refresh_from_db()
    assert contact.display_name == "Protected Contact"
    assert contact.avatar_path == "public/avatars/contacts/protected.webp"
