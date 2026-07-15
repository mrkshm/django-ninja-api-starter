import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image as PillowImage

from accounts.services import issue_token_pair
from contacts.models import Contact
from images.models import Image
from organizations.models import Membership, Organization
from tags.models import Tag

User = get_user_model()


def headers_for(user):
    access, _refresh = issue_token_pair(user)
    return {"Authorization": f"Bearer {access}"}


def image_upload(*, name: str = "image.png", color: str = "blue"):
    buffer = io.BytesIO()
    PillowImage.new("RGB", (16, 16), color=color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@pytest.fixture
def routed_tenant():
    owner = User.objects.create_user(email="route-owner@example.com", password="pw")
    admin = User.objects.create_user(email="route-admin@example.com", password="pw")
    member = User.objects.create_user(email="route-member@example.com", password="pw")
    outsider = User.objects.create_user(
        email="route-outsider@example.com", password="pw"
    )
    organization = Organization.objects.create(
        name="Routed", slug="routed", type="group"
    )
    Membership.objects.create(user=owner, organization=organization, role="owner")
    Membership.objects.create(user=admin, organization=organization, role="admin")
    Membership.objects.create(user=member, organization=organization, role="member")
    contact = Contact.objects.create(
        display_name="Routed Contact",
        slug="routed-contact",
        organization=organization,
        creator=owner,
    )
    Tag.objects.create(organization=organization, name="Routed", slug="routed")
    Image.objects.create(
        organization=organization,
        creator=owner,
        file="private/images/routed.webp",
    )
    return organization, contact, owner, admin, member, outsider


@pytest.mark.django_db
def test_route_families_hide_unknown_and_inaccessible_tenants(
    api_client,
    routed_tenant,
):
    organization, _contact, _owner, _admin, _member, outsider = routed_tenant
    headers = headers_for(outsider)
    path_templates = [
        "/orgs/{slug}/contacts/",
        "/orgs/{slug}/tags/",
        "/orgs/{slug}/images/",
        "/orgs/{slug}/exports/",
    ]

    for template in path_templates:
        inaccessible = api_client.get(
            template.format(slug=organization.slug), headers=headers
        )
        unknown = api_client.get(
            template.format(slug="does-not-exist"), headers=headers
        )
        assert inaccessible.status_code == unknown.status_code == 404
        assert (
            inaccessible.json()
            == unknown.json()
            == {"detail": "Organization not found"}
        )


@pytest.mark.django_db
def test_routed_roles_enforce_member_and_admin_boundaries(api_client, routed_tenant):
    organization, _contact, owner, admin, member, _outsider = routed_tenant
    ordinary_paths = [
        f"/orgs/{organization.slug}/contacts/",
        f"/orgs/{organization.slug}/tags/",
        f"/orgs/{organization.slug}/images/",
    ]
    for user in (owner, admin, member):
        for path in ordinary_paths:
            assert api_client.get(path, headers=headers_for(user)).status_code == 200

    export_path = f"/orgs/{organization.slug}/exports/"
    assert api_client.get(export_path, headers=headers_for(owner)).status_code == 200
    assert api_client.get(export_path, headers=headers_for(admin)).status_code == 200
    member_response = api_client.get(export_path, headers=headers_for(member))
    assert member_response.status_code == 403


@pytest.mark.django_db
def test_json_idempotency_runs_through_router(api_client, routed_tenant):
    organization, contact, owner, _admin, _member, _outsider = routed_tenant
    first = Image.objects.create(
        organization=organization, creator=owner, file="private/images/first.webp"
    )
    second = Image.objects.create(
        organization=organization, creator=owner, file="private/images/second.webp"
    )
    path = (
        f"/orgs/{organization.slug}/images/contacts/contact/{contact.pk}/"
        "bulk_attach/"
    )
    headers = {**headers_for(owner), "Idempotency-Key": "routed-json-key"}

    initial = api_client.post(path, json={"image_ids": [first.pk]}, headers=headers)
    replay = api_client.post(path, json={"image_ids": [first.pk]}, headers=headers)
    conflict = api_client.post(path, json={"image_ids": [second.pk]}, headers=headers)

    assert initial.status_code == replay.status_code == 200
    assert initial.json() == replay.json()
    assert conflict.status_code == 409


@pytest.mark.django_db
def test_multipart_idempotency_hashes_real_file_bytes(api_client, routed_tenant):
    organization, _contact, owner, _admin, _member, _outsider = routed_tenant
    path = f"/orgs/{organization.slug}/bulk-upload/"
    headers = {**headers_for(owner), "Idempotency-Key": "routed-file-key"}

    initial = api_client.post(
        path,
        data={},
        FILES={"files": [image_upload(color="blue")]},
        headers=headers,
    )
    replay = api_client.post(
        path,
        data={},
        FILES={"files": [image_upload(color="blue")]},
        headers=headers,
    )
    conflict = api_client.post(
        path,
        data={},
        FILES={"files": [image_upload(color="red")]},
        headers=headers,
    )

    assert initial.status_code == replay.status_code == 200
    assert initial.json() == replay.json()
    assert conflict.status_code == 409
