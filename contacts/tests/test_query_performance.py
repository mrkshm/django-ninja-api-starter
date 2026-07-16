import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from contacts.models import Contact
from contacts.schemas import ContactIn, ContactOut, ContactUpdate
from contacts.services import (
    contact_response_queryset,
    create_contact_record,
    update_contact_record,
)
from organizations.models import Membership, Organization
from tags.models import Tag, TaggedItem

User = get_user_model()


@pytest.mark.django_db
def test_new_contact_response_serialization_issues_no_queries():
    user = User.objects.create_user(email="create-query@example.com", password="pw")
    organization = Organization.objects.create(
        name="Create query", slug="create-query", type="group"
    )
    Membership.objects.create(user=user, organization=organization, role="owner")
    contact = create_contact_record(
        organization,
        user,
        ContactIn(display_name="New contact"),
    )

    with CaptureQueriesContext(connection) as queries:
        result = ContactOut.model_validate(contact)

    assert result.tags == []
    assert len(queries) == 0, [query["sql"] for query in queries.captured_queries]


@pytest.mark.django_db
def test_updated_contact_response_serialization_uses_prefetched_relations():
    user = User.objects.create_user(email="update-query@example.com", password="pw")
    organization = Organization.objects.create(
        name="Update query", slug="update-query", type="group"
    )
    Membership.objects.create(user=user, organization=organization, role="owner")
    contact = Contact.objects.create(
        display_name="Update contact",
        slug="update-contact",
        organization=organization,
        creator=user,
    )
    tag = Tag.objects.create(organization=organization, name="VIP", slug="vip")
    TaggedItem.objects.create(tag=tag, content_object=contact)
    contact = contact_response_queryset().get(pk=contact.pk)
    contact = update_contact_record(contact, ContactUpdate(phone="+33123456789"))

    with CaptureQueriesContext(connection) as queries:
        result = ContactOut.model_validate(contact)

    assert [item.name for item in result.tags] == ["VIP"]
    assert len(queries) == 0, [query["sql"] for query in queries.captured_queries]
