import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from tags.models import Tag, TaggedItem
from contacts.models import Contact
from organizations.models import Organization, Membership
from django.db import IntegrityError

User = get_user_model()

# Helper to login the test client as a user
from ninja.testing.client import TestClient as NinjaTestClient

def login_client(client: NinjaTestClient, user):
    response = client.post("/token/pair", json={"email": user.email, "password": "pw"})
    token = response.json()["access"]
    client.headers = {"Authorization": f"Bearer {token}"}

@pytest.mark.django_db
def test_assign_tag_to_contact(api_client):
    org = Organization.objects.create(name="TestOrg", slug="testorg")
    user = User.objects.create_user(email="test@example.com", password="pw")
    contact = Contact.objects.create(display_name="Test C", organization=org, creator=user)
    Membership.objects.create(user=user, organization=org, role="owner")
    login_client(api_client, user)
    url = f"/orgs/{org.slug}/tags/contacts/contact/{contact.id}/"
    response = api_client.post(url, json=["vip", "newsletter"])
    assert response.status_code == 200
    data = response.json()
    assert set([tag["name"] for tag in data]) == {"vip", "newsletter"}
    assert all(tag["organization"] == org.id for tag in data)
    assert TaggedItem.objects.filter(object_id=contact.id, tag__name="vip").exists()
    assert TaggedItem.objects.filter(object_id=contact.id, tag__name="newsletter").exists()

@pytest.mark.django_db
def test_assign_duplicate_tag_to_contact(api_client):
    org = Organization.objects.create(name="TestOrg", slug="testorg")
    user = User.objects.create_user(email="test@example.com", password="pw")
    contact = Contact.objects.create(display_name="Test C", organization=org, creator=user)
    Tag.objects.create(organization=org, name="vip", slug="vip")
    Membership.objects.create(user=user, organization=org, role="owner")
    login_client(api_client, user)
    url = f"/orgs/{org.slug}/tags/contacts/contact/{contact.id}/"
    response1 = api_client.post(url, json=["vip"])
    response2 = api_client.post(url, json=["vip"])
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert TaggedItem.objects.filter(object_id=contact.id, tag__name="vip").count() == 1

@pytest.mark.django_db
def test_remove_tag_from_contact(api_client):
    org = Organization.objects.create(name="TestOrg", slug="testorg")
    user = User.objects.create_user(email="test@example.com", password="pw")
    contact = Contact.objects.create(display_name="Test C", organization=org, creator=user)
    tag = Tag.objects.create(organization=org, name="vip", slug="vip")
    TaggedItem.objects.create(tag=tag, content_object=contact)
    Membership.objects.create(user=user, organization=org, role="owner")
    login_client(api_client, user)
    url = f"/orgs/{org.slug}/tags/contacts/contact/{contact.id}/vip/"
    response = api_client.delete(url)
    assert response.status_code == 200
    assert not TaggedItem.objects.filter(object_id=contact.id, tag__name="vip").exists()

@pytest.mark.django_db
def test_assign_tag_to_multiple_models(api_client):
    org = Organization.objects.create(name="TestOrg", slug="testorg")
    user = User.objects.create_user(email="test@example.com", password="pw")
    contact = Contact.objects.create(display_name="Test C", organization=org, creator=user)
    tag = Tag.objects.create(organization=org, name="orgtag", slug="orgtag")
    TaggedItem.objects.create(tag=tag, content_object=org)
    TaggedItem.objects.create(tag=tag, content_object=contact)
    assert TaggedItem.objects.filter(object_id=contact.id, tag=tag).exists()
    assert TaggedItem.objects.filter(object_id=org.id, tag=tag).exists()

@pytest.mark.django_db
def test_tags_not_globally_unique(api_client):
    org1 = Organization.objects.create(name="Org1", slug="org1")
    org2 = Organization.objects.create(name="Org2", slug="org2")
    tag1 = Tag.objects.create(organization=org1, name="vip", slug="vip")
    tag2 = Tag.objects.create(organization=org2, name="vip", slug="vip")
    assert tag1.name == tag2.name
    assert tag1.organization != tag2.organization
    assert tag1.id != tag2.id

@pytest.mark.django_db
def test_tags_unique_within_organization(api_client):
    org = Organization.objects.create(name="Org", slug="org")
    Tag.objects.create(organization=org, name="vip", slug="vip")
    with pytest.raises(IntegrityError):
        Tag.objects.create(organization=org, name="vip", slug="vip")

@pytest.mark.django_db
def test_edit_tag_name(api_client):
    org = Organization.objects.create(name="EditOrg", slug="editorg")
    user = User.objects.create_user(email="edit@example.com", password="pw")
    Membership.objects.create(user=user, organization=org, role="owner")
    tag = Tag.objects.create(organization=org, name="old", slug="old")
    login_client(api_client, user)
    response = api_client.patch(f"/orgs/{org.slug}/tags/{tag.id}/", json={"name": "newname"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "newname"
    assert data["slug"] == "newname"
    assert data["organization"] == org.id
    tag.refresh_from_db()
    assert tag.name == "newname"
    assert tag.slug == "newname"

@pytest.mark.django_db
def test_edit_tag_name_conflict(api_client):
    org = Organization.objects.create(name="EditOrg2", slug="editorg2")
    user = User.objects.create_user(email="edit2@example.com", password="pw")
    Membership.objects.create(user=user, organization=org, role="owner")
    tag1 = Tag.objects.create(organization=org, name="foo", slug="foo")
    tag2 = Tag.objects.create(organization=org, name="bar", slug="bar")
    login_client(api_client, user)
    response = api_client.patch(f"/orgs/{org.slug}/tags/{tag2.id}/", json={"name": "foo"})
    assert response.status_code == 400
    assert b"already exists" in response.content

@pytest.mark.django_db
def test_tag_list_pagination(api_client):
    org = Organization.objects.create(name="PagOrg", slug="pagorg")
    user = User.objects.create_user(email="pag@example.com", password="pw")
    Membership.objects.create(user=user, organization=org, role="owner")
    for i in range(15):
        Tag.objects.create(organization=org, name=f"tag{i}", slug=f"tag{i}")
    login_client(api_client, user)
    response = api_client.get(f"/orgs/{org.slug}/tags/?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "count" in data
    assert len(data["items"]) == 10
    assert data["count"] == 15
