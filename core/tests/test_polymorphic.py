import pytest
from django.contrib.auth import get_user_model
from ninja.errors import HttpError

from contacts.models import Contact
from core.utils.polymorphic import resolve_org_for_request, resolve_org_scoped_content_object
from organizations.models import Membership, Organization


class DummyRequest:
    def __init__(self, user):
        self.user = user
        self.auth = user


@pytest.fixture
def user_model():
    return get_user_model()


@pytest.fixture
def member_user(user_model):
    return user_model.objects.create_user(email="member@example.com", password="pw")


@pytest.fixture
def nonmember_user(user_model):
    return user_model.objects.create_user(email="nonmember@example.com", password="pw")


@pytest.fixture
def org(member_user):
    organization = Organization.objects.create(name="Org", slug="org", type="group")
    Membership.objects.create(user=member_user, organization=organization, role="member")
    return organization


@pytest.mark.django_db
def test_resolve_org_for_request_allows_members(member_user, org):
    assert resolve_org_for_request(DummyRequest(member_user), org.slug) == org


@pytest.mark.django_db
def test_resolve_org_for_request_rejects_non_members(nonmember_user, org):
    with pytest.raises(HttpError) as exc_info:
        resolve_org_for_request(DummyRequest(nonmember_user), org.slug)

    assert exc_info.value.status_code == 403


@pytest.mark.django_db
def test_resolve_org_scoped_content_object_allows_member_object(member_user, org):
    contact = Contact.objects.create(display_name="Jane", organization=org, creator=member_user)

    resolved = resolve_org_scoped_content_object(
        DummyRequest(member_user),
        org.slug,
        "contacts",
        "contact",
        contact.id,
    )

    assert resolved.organization == org
    assert resolved.content_type.app_label == "contacts"
    assert resolved.content_type.model == "contact"
    assert resolved.obj == contact


@pytest.mark.django_db
def test_resolve_org_scoped_content_object_rejects_cross_org_object(member_user, org):
    other_org = Organization.objects.create(name="Other", slug="other", type="group")
    contact = Contact.objects.create(display_name="Jane", organization=other_org, creator=member_user)

    with pytest.raises(HttpError) as exc_info:
        resolve_org_scoped_content_object(
            DummyRequest(member_user),
            org.slug,
            "contacts",
            "contact",
            contact.id,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.django_db
def test_resolve_org_scoped_content_object_rejects_non_member(nonmember_user, org):
    contact = Contact.objects.create(display_name="Jane", organization=org, creator=nonmember_user)

    with pytest.raises(HttpError) as exc_info:
        resolve_org_scoped_content_object(
            DummyRequest(nonmember_user),
            org.slug,
            "contacts",
            "contact",
            contact.id,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.django_db
def test_resolve_org_scoped_content_object_unknown_type_raises_404(member_user, org):
    with pytest.raises(HttpError) as exc_info:
        resolve_org_scoped_content_object(
            DummyRequest(member_user),
            org.slug,
            "contacts",
            "missingmodel",
            1,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.django_db
def test_resolve_org_scoped_content_object_missing_object_raises_404(member_user, org):
    with pytest.raises(HttpError) as exc_info:
        resolve_org_scoped_content_object(
            DummyRequest(member_user),
            org.slug,
            "contacts",
            "contact",
            999999,
        )

    assert exc_info.value.status_code == 404
