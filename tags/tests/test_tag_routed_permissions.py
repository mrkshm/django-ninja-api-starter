import pytest

from accounts.models import User
from accounts.services import issue_token_pair
from contacts.models import Contact
from organizations.models import Membership, Organization
from tags.models import Tag


def headers_for(user: User) -> dict[str, str]:
    access, _refresh = issue_token_pair(user)
    return {"Authorization": f"Bearer {access}"}


@pytest.mark.django_db
def test_outsider_cannot_use_any_tag_read_or_mutation_route(api_client):
    owner = User.objects.create_user(email="tag-owner@example.com", password="pw")
    outsider = User.objects.create_user(email="tag-outsider@example.com", password="pw")
    organization = Organization.objects.create(
        name="Tag Permissions", slug="tag-permissions", type="group"
    )
    Membership.objects.create(user=owner, organization=organization, role="owner")
    contact = Contact.objects.create(
        display_name="Tag Target",
        slug="tag-target",
        organization=organization,
        creator=owner,
    )
    tag = Tag.objects.create(
        organization=organization,
        name="Protected",
        slug="protected",
    )
    headers = headers_for(outsider)
    collection = f"/orgs/{organization.slug}/tags/"
    object_path = f"{collection}contacts/contact/{contact.pk}/"

    responses = [
        api_client.get(collection, headers=headers),
        api_client.get(f"{collection}search/?q=protected", headers=headers),
        api_client.get(f"{collection}by-slug/{tag.slug}/", headers=headers),
        api_client.get(object_path, headers=headers),
        api_client.post(
            object_path,
            json=["forbidden"],
            headers=headers,
        ),
        api_client.patch(
            f"{collection}{tag.pk}/",
            json={"name": "Forbidden"},
            headers=headers,
        ),
        api_client.delete(f"{collection}{tag.pk}/", headers=headers),
        api_client.delete(object_path, json=[tag.pk], headers=headers),
        api_client.delete(f"{object_path}{tag.slug}/", headers=headers),
    ]

    assert [(response.status_code, response.json()) for response in responses] == [
        (404, {"detail": "Organization not found"})
    ] * len(responses)
    tag.refresh_from_db()
    assert tag.name == "Protected"
