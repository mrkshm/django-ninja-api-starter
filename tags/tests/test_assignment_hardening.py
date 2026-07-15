from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType

from accounts.tests.utils import create_test_user
from contacts.models import Contact
from organizations.models import Membership, Organization
from tags.models import Tag, TaggedItem
from tags.services import assign_tags_to_object
from tags.validation import MAX_TAGS_PER_ASSIGNMENT


@pytest.fixture
def tag_context(api_client, make_auth_headers):
    user = create_test_user(email="tag-hardening@example.com", password="pw")
    organization = Organization.objects.create(
        name="Tag hardening",
        slug="tag-hardening",
        type="group",
        creator=user,
    )
    Membership.objects.create(user=user, organization=organization, role="owner")
    contact = Contact.objects.create(
        display_name="Tagged contact",
        slug="tagged-contact",
        organization=organization,
        creator=user,
    )
    headers = make_auth_headers(api_client, user, password="pw")
    url = f"/orgs/{organization.slug}/tags/contacts/contact/{contact.id}/"
    return organization, contact, headers, url


@pytest.mark.django_db
def test_assignment_deduplicates_without_renaming_existing_tag(api_client, tag_context):
    organization, contact, headers, url = tag_context
    tag = Tag.objects.create(organization=organization, name="VIP", slug="vip")

    response = api_client.post(url, json=["vip", " VIP "], headers=headers)

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["VIP"]
    tag.refresh_from_db()
    assert tag.name == "VIP"
    assert TaggedItem.objects.filter(tag=tag, object_id=contact.id).count() == 1


@pytest.mark.django_db
def test_assignment_rejects_distinct_names_with_same_slug(api_client, tag_context):
    organization, contact, headers, url = tag_context
    existing = Tag.objects.create(organization=organization, name="C++", slug="c")

    response = api_client.post(url, json=["C#"], headers=headers)

    assert response.status_code == 409
    existing.refresh_from_db()
    assert existing.name == "C++"
    assert not TaggedItem.objects.filter(tag=existing, object_id=contact.id).exists()


@pytest.mark.django_db
def test_assignment_rejects_more_than_fifty_names(api_client, tag_context):
    organization, _contact, headers, url = tag_context

    response = api_client.post(
        url,
        json=[f"tag-{index}" for index in range(MAX_TAGS_PER_ASSIGNMENT + 1)],
        headers=headers,
    )

    assert response.status_code == 400
    assert not Tag.objects.filter(organization=organization).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("name", [" ", "!?!", "x" * 51])
def test_assignment_rejects_invalid_names(api_client, tag_context, name):
    organization, _contact, headers, url = tag_context

    response = api_client.post(url, json=[name], headers=headers)

    assert response.status_code == 400
    assert not Tag.objects.filter(organization=organization).exists()


@pytest.mark.django_db
def test_assignment_rolls_back_new_tags_when_relation_creation_fails(tag_context):
    organization, contact, _headers, _url = tag_context
    content_type = ContentType.objects.get_for_model(Contact)

    with (
        patch.object(
            TaggedItem.objects,
            "bulk_create",
            side_effect=RuntimeError("relation write failed"),
        ),
        pytest.raises(RuntimeError, match="relation write failed"),
    ):
        assign_tags_to_object(
            organization,
            content_type,
            contact.id,
            ["Transactional"],
        )

    assert not Tag.objects.filter(
        organization=organization,
        slug="transactional",
    ).exists()


@pytest.mark.django_db
def test_create_and_rename_share_tag_name_normalization(api_client, tag_context):
    organization, _contact, headers, _url = tag_context

    create_response = api_client.post(
        f"/orgs/{organization.slug}/tags/",
        json={"name": " VIP "},
        headers=headers,
    )
    assert create_response.status_code == 200
    assert create_response.json()["name"] == "VIP"

    rename_response = api_client.patch(
        f"/orgs/{organization.slug}/tags/{create_response.json()['id']}/",
        json={"name": " Priority "},
        headers=headers,
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "Priority"
    assert rename_response.json()["slug"] == "priority"
