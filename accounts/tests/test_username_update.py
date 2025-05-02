import pytest
from django.contrib.auth import get_user_model
from ninja.testing import TestClient
from DjangoApiStarter.api import api
from ninja.main import NinjaAPI
from organizations.models import Organization, Membership

User = get_user_model()
client = TestClient(api)

@pytest.fixture(autouse=True)
def clear_ninjaapi_registry():
    NinjaAPI._registry.clear()

@pytest.mark.django_db
def test_patch_username_success():
    user = User.objects.create_user(email="me@example.com", password="testpass", username="oldname")
    # Clean up any existing personal orgs for this user
    Organization.objects.filter(memberships__user=user, type="personal").delete()
    org = Organization.objects.create(name="oldname", slug="oldname-success", type="personal")
    Membership.objects.create(user=user, organization=org, role="owner")
    response = client.post("/token/pair", json={"email": "me@example.com", "password": "testpass"})
    access = response.json()["access"]
    response = client.patch("/users/username", json={"username": "newname"}, headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "newname"
    assert data["slug"] == "newname"
    assert data["org_name"] == "newname"
    assert data["org_slug"] == "newname"
    # Ensure DB updated
    user.refresh_from_db()
    org.refresh_from_db()
    # Re-fetch org by id to ensure we check the updated org
    updated_org = Organization.objects.get(id=org.id)
    assert updated_org.name == "newname"
    assert updated_org.slug == "newname"
    assert user.username == "newname"
    assert user.slug == "newname"
    assert org.name == "newname"
    assert org.slug == "newname"

@pytest.mark.django_db
def test_patch_username_taken():
    user1 = User.objects.create_user(email="me@example.com", password="testpass", username="oldname")
    user2 = User.objects.create_user(email="other@example.com", password="testpass", username="takenname")
    # Clean up any existing personal orgs for this user
    Organization.objects.filter(memberships__user=user1, type="personal").delete()
    org = Organization.objects.create(name="oldname", slug="oldname-taken", type="personal")
    Membership.objects.create(user=user1, organization=org, role="owner")
    response = client.post("/token/pair", json={"email": "me@example.com", "password": "testpass"})
    access = response.json()["access"]
    response = client.patch("/users/username", json={"username": "takenname"}, headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 400
    assert "Username already taken" in response.json()["detail"]

@pytest.mark.django_db
def test_patch_username_empty():
    user = User.objects.create_user(email="me2@example.com", password="testpass", username="oldname2")
    Organization.objects.filter(memberships__user=user, type="personal").delete()
    org = Organization.objects.create(name="oldname2", slug="oldname2-empty", type="personal")
    Membership.objects.create(user=user, organization=org, role="owner")
    response = client.post("/token/pair", json={"email": "me2@example.com", "password": "testpass"})
    access = response.json()["access"]
    response = client.patch("/users/username", json={"username": "   "}, headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 400
    assert "Username cannot be empty" in response.json()["detail"]

@pytest.mark.django_db
def test_patch_username_org_missing():
    user = User.objects.create_user(email="me3@example.com", password="testpass", username="oldname3")
    # Ensure no personal org exists for user
    Organization.objects.filter(memberships__user=user, type="personal").delete()
    response = client.post("/token/pair", json={"email": "me3@example.com", "password": "testpass"})
    access = response.json()["access"]
    response = client.patch("/users/username", json={"username": "newname3"}, headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 500
    assert "Personal organization not found for user" in response.json()["detail"]
