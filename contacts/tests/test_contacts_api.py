import pytest
from django.contrib.auth import get_user_model
from organizations.models import Organization
from contacts.models import Contact
from DjangoApiStarter.api import api
from ninja.testing import TestClient
from ninja.main import NinjaAPI
from ninja_jwt.controller import NinjaJWTDefaultController
import io
from PIL import Image
from django.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()
client = TestClient(api)

@pytest.fixture(autouse=True)
def clear_ninjaapi_registry():
    NinjaAPI._registry.clear()
    api.register_controllers(NinjaJWTDefaultController)

@pytest.mark.django_db
def test_create_contact():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    payload = {"display_name": "Alice", "organization": org.slug}
    resp = client.post("/contacts/", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Alice"
    assert data["organization"] == org.slug
    assert "slug" in data
    assert data["creator"] == user.slug

@pytest.mark.django_db
def test_get_contact():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    contact = Contact.objects.create(display_name="Bob", slug="bob", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    resp = client.get(f"/contacts/{contact.slug}/", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Bob"
    assert data["organization"] == org.slug
    assert data["creator"] == user.slug

@pytest.mark.django_db
def test_update_contact_display_name_and_slug():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    contact = Contact.objects.create(display_name="Charlie", slug="charlie", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    payload = {"display_name": "Charlie Brown"}
    resp = client.patch(f"/contacts/{contact.slug}/", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Charlie Brown"
    assert data["slug"] != "charlie"

@pytest.mark.django_db
def test_list_contacts():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    Contact.objects.create(display_name="X", slug="x", organization=org, creator=user)
    Contact.objects.create(display_name="Y", slug="y", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    resp = client.get("/contacts/", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["count"] == 2
    display_names = {item["display_name"] for item in data["items"]}
    assert display_names == {"X", "Y"}

@pytest.mark.django_db
def test_delete_contact():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    contact = Contact.objects.create(display_name="Z", slug="z", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    resp = client.delete(f"/contacts/{contact.slug}/", headers=headers)
    assert resp.status_code == 200
    assert not Contact.objects.filter(slug="z").exists()

@pytest.mark.django_db
def test_auth_required():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    payload = {"display_name": "NoAuth", "organization": org.slug}
    resp = client.post("/contacts/", json=payload)
    assert resp.status_code == 401

@pytest.mark.django_db
def test_invalid_org_slug():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    payload = {"display_name": "BadOrg", "organization": "does-not-exist"}
    resp = client.post("/contacts/", json=payload, headers=headers)
    assert resp.status_code == 404

@pytest.mark.django_db
def test_missing_name():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    payload = {"organization": org.slug}
    resp = client.post("/contacts/", json=payload, headers=headers)
    assert resp.status_code == 400

@pytest.mark.django_db
def test_get_nonexistent_contact():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    resp = client.get("/contacts/not-a-real-slug/", headers=headers)
    assert resp.status_code == 404

@pytest.mark.django_db
def test_upload_contact_avatar(tmp_path):
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    contact = Contact.objects.create(display_name="AvatarTest", slug="avatartest", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    django_client = Client()
    # Upload avatar
    img = Image.new("RGB", (300, 300), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    uploaded = SimpleUploadedFile("avatar.png", buf.getvalue(), content_type="image/png")
    response = django_client.post(
        f"/api/v1/contacts/{contact.slug}/avatar/",
        {"file": uploaded},
        HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert response.status_code == 200, response.content
    data = response.json()
    assert "avatar_path" in data
    assert data["avatar_path"].endswith(".webp")
    contact.refresh_from_db()
    assert contact.avatar_path == data["avatar_path"]

@pytest.mark.django_db
def test_upload_contact_avatar_invalid_type():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    contact = Contact.objects.create(display_name="AvatarTest2", slug="avatartest2", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    django_client = Client()
    buf = io.BytesIO(b"not an image")
    uploaded = SimpleUploadedFile("notanimage.txt", buf.getvalue(), content_type="text/plain")
    response = django_client.post(
        f"/api/v1/contacts/{contact.slug}/avatar/",
        {"file": uploaded},
        HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert response.status_code == 400
    assert "detail" in response.json()

@pytest.mark.django_db
def test_delete_contact_avatar():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    contact = Contact.objects.create(display_name="AvatarTestDel", slug="avatartestdel", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    django_client = Client()
    # Upload avatar
    img = Image.new("RGB", (300, 300), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    uploaded = SimpleUploadedFile("avatar.png", buf.getvalue(), content_type="image/png")
    upload_resp = django_client.post(
        f"/api/v1/contacts/{contact.slug}/avatar/",
        {"file": uploaded},
        HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert upload_resp.status_code == 200
    contact.refresh_from_db()
    assert contact.avatar_path is not None
    # Delete avatar
    del_resp = django_client.delete(
        f"/api/v1/contacts/{contact.slug}/avatar/",
        HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["detail"] == "Avatar deleted."
    contact.refresh_from_db()
    assert contact.avatar_path is None

@pytest.mark.django_db
def test_delete_contact_avatar_no_avatar():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    contact = Contact.objects.create(display_name="NoAvatar", slug="noavatar", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    django_client = Client()
    del_resp = django_client.delete(
        f"/api/v1/contacts/{contact.slug}/avatar/",
        HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert del_resp.status_code == 404
    assert del_resp.json()["detail"] == "No avatar to delete."

@pytest.mark.django_db
def test_upload_contact_avatar_too_large():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    contact = Contact.objects.create(display_name="BigAvatar", slug="bigavatar", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    django_client = Client()
    # Create a file just over 10MB
    data = b"0" * (10 * 1024 * 1024 + 1)
    uploaded = SimpleUploadedFile("big.png", data, content_type="image/png")
    upload_resp = django_client.post(
        f"/api/v1/contacts/{contact.slug}/avatar/",
        {"file": uploaded},
        HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert upload_resp.status_code == 400
    assert upload_resp.json()["detail"] == "File too large. Maximum allowed size is 10MB."
