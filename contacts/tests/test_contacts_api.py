import pytest
from django.contrib.auth import get_user_model
from organizations.models import Organization, Membership
from contacts.models import Contact
from DjangoApiStarter.api import api
from ninja.testing import TestClient
from ninja.main import NinjaAPI
from ninja_jwt.controller import NinjaJWTDefaultController
import io
from PIL import Image
from django.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict

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
    Membership.objects.create(user=user, organization=org, role="owner")
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
    Membership.objects.create(user=user, organization=org, role="owner")
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
    Membership.objects.create(user=user, organization=org, role="owner")
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
    Membership.objects.create(user=user, organization=org, role="owner")
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
    Membership.objects.create(user=user, organization=org, role="owner")
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
    errors = resp.json()
    assert isinstance(errors, dict)
    assert "detail" in errors
    assert "at least one of display_name" in errors["detail"].lower()

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
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(display_name="AvatarTest", slug="avatartest", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    img = Image.new("RGB", (300, 300), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    uploaded = SimpleUploadedFile("avatar.png", buf.getvalue(), content_type="image/png")
    files = MultiValueDict({"file": [uploaded]})
    response = client.post(
        f"/contacts/{contact.slug}/avatar/",
        data={},
        FILES=files,
        headers=headers,
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
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(display_name="AvatarTest2", slug="avatartest2", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    buf = io.BytesIO(b"not an image")
    uploaded = SimpleUploadedFile("notanimage.txt", buf.getvalue(), content_type="text/plain")
    files = MultiValueDict({"file": [uploaded]})
    response = client.post(
        f"/contacts/{contact.slug}/avatar/",
        data={},
        FILES=files,
        headers=headers,
    )
    assert response.status_code == 400
    assert "detail" in response.json()

@pytest.mark.django_db
def test_delete_contact_avatar():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(display_name="AvatarTestDel", slug="avatartestdel", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    # Upload avatar
    img = Image.new("RGB", (300, 300), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    uploaded = SimpleUploadedFile("avatar.png", buf.getvalue(), content_type="image/png")
    files = MultiValueDict({"file": [uploaded]})
    upload_resp = client.post(
        f"/contacts/{contact.slug}/avatar/",
        data={},
        FILES=files,
        headers=headers,
    )
    assert upload_resp.status_code == 200
    contact.refresh_from_db()
    assert contact.avatar_path is not None
    # Delete avatar
    del_resp = client.delete(f"/contacts/{contact.slug}/avatar/", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["detail"] == "Avatar deleted."
    contact.refresh_from_db()
    assert contact.avatar_path is None

@pytest.mark.django_db
def test_delete_contact_avatar_no_avatar():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(display_name="NoAvatar", slug="noavatar", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    del_resp = client.delete(f"/contacts/{contact.slug}/avatar/", headers=headers)
    assert del_resp.status_code == 404
    assert del_resp.json()["detail"] == "No avatar to delete."

@pytest.mark.django_db
def test_upload_contact_avatar_too_large():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Test Org", slug="test-org", type="group", creator=user)
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(display_name="BigAvatar", slug="bigavatar", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    # Create a file just over 10MB
    data = b"0" * (10 * 1024 * 1024 + 1)
    uploaded = SimpleUploadedFile("big.png", data, content_type="image/png")
    files = MultiValueDict({"file": [uploaded]})
    upload_resp = client.post(
        f"/contacts/{contact.slug}/avatar/",
        data={},
        FILES=files,
        headers=headers,
    )
    assert upload_resp.status_code == 400
    assert upload_resp.json()["detail"] == "File too large. Maximum allowed size is 10MB."

@pytest.mark.django_db
def test_create_contact_display_name_logic():
    user = User.objects.create_user(email="logic@example.com", password="pw", username="logicuser", slug="logicuser")
    org = Organization.objects.create(name="Logic Org", slug="logic-org", type="group", creator=user)
    Membership.objects.create(user=user, organization=org, role="owner")
    resp = client.post("/token/pair", json={"email": "logic@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    # Case 1: Only first_name and last_name
    payload = {"organization": org.slug, "first_name": "Jane", "last_name": "Doe"}
    resp = client.post("/contacts/", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Jane Doe"
    # Case 2: Only first_name (unique)
    payload = {"organization": org.slug, "first_name": "Solo2"}
    resp = client.post("/contacts/", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Solo2"
    # Case 3: Only last_name (unique)
    payload = {"organization": org.slug, "last_name": "Surname3"}
    resp = client.post("/contacts/", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Surname3"
    # Case 4: No names at all
    payload = {"organization": org.slug}
    resp = client.post("/contacts/", json=payload, headers=headers)
    assert resp.status_code == 400
    errors = resp.json()
    assert isinstance(errors, dict)
    assert "detail" in errors
    assert "at least one of display_name" in errors["detail"].lower()

@pytest.mark.django_db
def test_update_contact_organization_and_fields():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org1 = Organization.objects.create(name="Org1", slug="org1", type="group", creator=user)
    org2 = Organization.objects.create(name="Org2", slug="org2", type="group", creator=user)
    Membership.objects.create(user=user, organization=org1, role="owner")
    Membership.objects.create(user=user, organization=org2, role="owner")
    contact = Contact.objects.create(display_name="Original Name", slug="original-name", organization=org1, creator=user, email="old@email.com", phone="12345")
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    payload = {
        "display_name": "New Name",
        "organization": org2.slug,
        "email": "new@email.com",
        "phone": "67890"
    }
    resp = client.put(f"/contacts/{contact.slug}/", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "New Name"
    assert data["organization"] == org2.slug
    assert data["email"] == "new@email.com"
    assert data["phone"] == "67890"
    # Confirm DB update
    contact.refresh_from_db()
    assert contact.display_name == "New Name"
    assert contact.organization == org2
    assert contact.email == "new@email.com"
    assert contact.phone == "67890"
    # Error case: invalid organization slug
    payload["organization"] = "does-not-exist"
    resp = client.put(f"/contacts/{contact.slug}/", json=payload, headers=headers)
    assert resp.status_code == 404

@pytest.mark.django_db
def test_upload_contact_avatar_error(monkeypatch):
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org = Organization.objects.create(name="Avatar Org", slug="avatar-org", type="group", creator=user)
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(display_name="AvatarFail", slug="avatarfail", organization=org, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    # Monkeypatch resize_avatar_images to raise Exception
    def fail_resize(*a, **kw):
        raise Exception("resize failed")
    monkeypatch.setattr("core.utils.image.resize_avatar_images", fail_resize)
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.utils.datastructures import MultiValueDict
    uploaded = SimpleUploadedFile("fail.png", b"fake", content_type="image/png")
    files = MultiValueDict({"file": [uploaded]})
    resp = client.post(
        f"/contacts/{contact.slug}/avatar/",
        data={},
        FILES=files,
        headers=headers,
    )
    assert resp.status_code == 400
    assert "failed to process avatar" in resp.json()["detail"].lower()

@pytest.mark.django_db
def test_partial_update_contact_organization():
    user = User.objects.create_user(email="test@example.com", password="pw", username="testuser", slug="testuser")
    org1 = Organization.objects.create(name="Org1Patch", slug="org1patch", type="group", creator=user)
    org2 = Organization.objects.create(name="Org2Patch", slug="org2patch", type="group", creator=user)
    Membership.objects.create(user=user, organization=org1, role="owner")
    Membership.objects.create(user=user, organization=org2, role="owner")
    contact = Contact.objects.create(display_name="Patch Name", slug="patch-name", organization=org1, creator=user)
    resp = client.post("/token/pair", json={"email": "test@example.com", "password": "pw"})
    access = resp.json()["access"]
    headers = {"Authorization": f"Bearer {access}"}
    # Patch organization only
    payload = {"organization": org2.slug}
    resp = client.patch(f"/contacts/{contact.slug}/", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["organization"] == org2.slug
    contact.refresh_from_db()
    assert contact.organization == org2
    # Error case: invalid organization slug
    payload = {"organization": "does-not-exist"}
    resp = client.patch(f"/contacts/{contact.slug}/", json=payload, headers=headers)
    assert resp.status_code == 404
