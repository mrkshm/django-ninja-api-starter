import io
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict
from PIL import Image

from accounts.tests.utils import create_test_user
from contacts.models import Contact
from organizations.models import Membership, Organization

User = get_user_model()


@pytest.mark.django_db
def test_create_contact(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    headers = make_auth_headers(api_client, user, password="pw")
    payload = {
        "display_name": "Alice",
    }
    resp = api_client.post(f"/orgs/{org.slug}/contacts/", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Alice"
    assert data["organization"] == org.slug
    assert "slug" in data
    assert data["creator"] == user.slug


@pytest.mark.django_db
def test_contact_slugs_are_unique_per_organization(make_auth_headers, api_client):
    user = create_test_user(email="scoped-slug@example.com", password="pw")
    first = Organization.objects.create(
        name="First", slug="contact-first", type="group"
    )
    second = Organization.objects.create(
        name="Second", slug="contact-second", type="group"
    )
    Membership.objects.create(user=user, organization=first, role="member")
    Membership.objects.create(user=user, organization=second, role="member")
    headers = make_auth_headers(api_client, user, password="pw")

    first_response = api_client.post(
        f"/orgs/{first.slug}/contacts/", json={"display_name": "Alex"}, headers=headers
    )
    second_response = api_client.post(
        f"/orgs/{second.slug}/contacts/", json={"display_name": "Alex"}, headers=headers
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["slug"] == second_response.json()["slug"] == "alex"


@pytest.mark.django_db
def test_get_contact(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(
        display_name="Bob", slug="bob", organization=org, creator=user
    )
    headers = make_auth_headers(api_client, user, password="pw")
    resp = api_client.get(f"/orgs/{org.slug}/contacts/{contact.slug}/", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Bob"
    assert data["organization"] == org.slug
    assert data["creator"] == user.slug


@pytest.mark.django_db
def test_update_contact_display_name_and_slug(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(
        display_name="Charlie", slug="charlie", organization=org, creator=user
    )
    headers = make_auth_headers(api_client, user, password="pw")
    payload = {"display_name": "Charlie Brown"}
    resp = api_client.patch(
        f"/orgs/{org.slug}/contacts/{contact.slug}/", json=payload, headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Charlie Brown"
    assert data["slug"] != "charlie"


@pytest.mark.django_db
def test_partial_update_contact_location_and_notes(make_auth_headers, api_client):
    user = create_test_user(email="patch-contact-fields@example.com", password="pw")
    org = Organization.objects.create(
        name="Patch Contact Fields",
        slug="patch-contact-fields",
        type="group",
        creator=user,
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(
        display_name="Patch Fields",
        slug="patch-fields",
        organization=org,
        creator=user,
    )
    headers = make_auth_headers(api_client, user, password="pw")

    response = api_client.patch(
        f"/orgs/{org.slug}/contacts/{contact.slug}/",
        json={"location": "Paris", "notes": "Met at DjangoCon"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["location"] == "Paris"
    assert response.json()["notes"] == "Met at DjangoCon"
    contact.refresh_from_db()
    assert contact.location == "Paris"
    assert contact.notes == "Met at DjangoCon"


@pytest.mark.django_db
def test_partial_update_contact_clears_location_and_notes(
    make_auth_headers, api_client
):
    user = create_test_user(email="clear-contact-fields@example.com", password="pw")
    org = Organization.objects.create(
        name="Clear Contact Fields",
        slug="clear-contact-fields",
        type="group",
        creator=user,
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(
        display_name="Clear Fields",
        slug="clear-fields",
        location="Paris",
        notes="Remove me",
        organization=org,
        creator=user,
    )
    headers = make_auth_headers(api_client, user, password="pw")

    response = api_client.patch(
        f"/orgs/{org.slug}/contacts/{contact.slug}/",
        json={"location": None, "notes": None},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["location"] == ""
    assert response.json()["notes"] == ""
    contact.refresh_from_db()
    assert contact.location == ""
    assert contact.notes == ""


@pytest.mark.django_db
def test_list_contacts(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    Contact.objects.create(display_name="X", slug="x", organization=org, creator=user)
    Contact.objects.create(display_name="Y", slug="y", organization=org, creator=user)
    headers = make_auth_headers(api_client, user, password="pw")
    resp = api_client.get(f"/orgs/{org.slug}/contacts/", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["count"] == 2
    display_names = {item["display_name"] for item in data["items"]}
    assert display_names == {"X", "Y"}


@pytest.mark.django_db
def test_delete_contact(
    make_auth_headers, api_client, django_capture_on_commit_callbacks
):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(
        display_name="Z",
        slug="z",
        organization=org,
        creator=user,
        avatar_path="public/avatars/contacts/z.webp",
    )
    headers = make_auth_headers(api_client, user, password="pw")
    with patch("core.utils.avatar.delete_avatar_files") as delete_avatar_files:
        with django_capture_on_commit_callbacks(execute=True):
            resp = api_client.delete(
                f"/orgs/{org.slug}/contacts/{contact.slug}/", headers=headers
            )
    assert resp.status_code == 200
    assert not Contact.objects.filter(slug="z").exists()
    delete_avatar_files.assert_called_once_with("public/avatars/contacts/z.webp")


@pytest.mark.django_db
def test_auth_required(api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    payload = {
        "display_name": "NoAuth",
    }
    resp = api_client.post(f"/orgs/{org.slug}/contacts/", json=payload)
    assert resp.status_code == 401


@pytest.mark.django_db
def test_invalid_org_slug(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    headers = make_auth_headers(api_client, user, password="pw")
    payload = {"display_name": "BadOrg"}
    resp = api_client.post(
        "/orgs/does-not-exist/contacts/", json=payload, headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_missing_name(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    headers = make_auth_headers(api_client, user, password="pw")
    payload = {}
    resp = api_client.post(f"/orgs/{org.slug}/contacts/", json=payload, headers=headers)
    assert resp.status_code == 400
    errors = resp.json()
    assert isinstance(errors, dict)
    assert "detail" in errors
    assert "at least one of display_name" in errors["detail"].lower()


@pytest.mark.django_db
def test_get_nonexistent_contact(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    headers = make_auth_headers(api_client, user, password="pw")
    resp = api_client.get(
        f"/orgs/{user.memberships.first().organization.slug}/contacts/not-a-real-slug/",
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_upload_contact_avatar(tmp_path, make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(
        display_name="AvatarTest", slug="avatartest", organization=org, creator=user
    )
    headers = make_auth_headers(api_client, user, password="pw")
    img = Image.new("RGB", (300, 300), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    uploaded = SimpleUploadedFile(
        "avatar.png", buf.getvalue(), content_type="image/png"
    )
    files = MultiValueDict({"file": [uploaded]})
    response = api_client.post(
        f"/orgs/{org.slug}/contacts/{contact.slug}/avatar/",
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
def test_upload_contact_avatar_invalid_type(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(
        display_name="AvatarTest2", slug="avatartest2", organization=org, creator=user
    )
    headers = make_auth_headers(api_client, user, password="pw")
    buf = io.BytesIO(b"not an image")
    uploaded = SimpleUploadedFile(
        "notanimage.txt", buf.getvalue(), content_type="text/plain"
    )
    files = MultiValueDict({"file": [uploaded]})
    response = api_client.post(
        f"/orgs/{org.slug}/contacts/{contact.slug}/avatar/",
        data={},
        FILES=files,
        headers=headers,
    )
    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.django_db
def test_delete_contact_avatar(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(
        display_name="AvatarTestDel",
        slug="avatartestdel",
        organization=org,
        creator=user,
    )
    headers = make_auth_headers(api_client, user, password="pw")
    # Upload avatar
    img = Image.new("RGB", (300, 300), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    uploaded = SimpleUploadedFile(
        "avatar.png", buf.getvalue(), content_type="image/png"
    )
    files = MultiValueDict({"file": [uploaded]})
    upload_resp = api_client.post(
        f"/orgs/{org.slug}/contacts/{contact.slug}/avatar/",
        data={},
        FILES=files,
        headers=headers,
    )
    assert upload_resp.status_code == 200
    contact.refresh_from_db()
    assert contact.avatar_path is not None
    # Delete avatar
    del_resp = api_client.delete(
        f"/orgs/{org.slug}/contacts/{contact.slug}/avatar/", headers=headers
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["detail"] == "Avatar deleted."
    contact.refresh_from_db()
    assert contact.avatar_path is None


@pytest.mark.django_db
def test_delete_contact_avatar_no_avatar(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(
        display_name="NoAvatar", slug="noavatar", organization=org, creator=user
    )
    headers = make_auth_headers(api_client, user, password="pw")
    del_resp = api_client.delete(
        f"/orgs/{org.slug}/contacts/{contact.slug}/avatar/", headers=headers
    )
    assert del_resp.status_code == 404
    assert del_resp.json()["detail"] == "No avatar to delete."


@pytest.mark.django_db
def test_get_contact_avatar_url_is_public(monkeypatch, api_client):
    def fake_public_storage_url(key):
        return f"https://storage.example/{key}"

    monkeypatch.setattr("contacts.api.public_storage_url", fake_public_storage_url)

    key = "public/avatars/contacts/0123456789abcdef0123456789abcdef.webp"
    resp = api_client.get(f"/avatars/{key}")

    assert resp.status_code == 200
    assert resp.json() == {"url": f"https://storage.example/{key}"}


@pytest.mark.django_db
def test_upload_contact_avatar_too_large(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Test Org", slug="test-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(
        display_name="BigAvatar", slug="bigavatar", organization=org, creator=user
    )
    headers = make_auth_headers(api_client, user, password="pw")
    # Create a file just over 10MB
    data = b"0" * (10 * 1024 * 1024 + 1)
    uploaded = SimpleUploadedFile("big.png", data, content_type="image/png")
    files = MultiValueDict({"file": [uploaded]})
    upload_resp = api_client.post(
        f"/orgs/{org.slug}/contacts/{contact.slug}/avatar/",
        data={},
        FILES=files,
        headers=headers,
    )
    assert upload_resp.status_code == 400
    assert (
        upload_resp.json()["detail"] == "File too large. Maximum allowed size is 10MB."
    )


@pytest.mark.django_db
def test_create_contact_display_name_logic(make_auth_headers, api_client):
    user = create_test_user(
        email="logic@example.com", password="pw", username="logicuser", slug="logicuser"
    )
    org = Organization.objects.create(
        name="Logic Org", slug="logic-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    headers = make_auth_headers(api_client, user, password="pw")
    # Case 1: Only first_name and last_name
    payload = {"first_name": "Jane", "last_name": "Doe"}
    resp = api_client.post(f"/orgs/{org.slug}/contacts/", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Jane Doe"
    # Case 2: Only first_name (unique)
    payload = {"first_name": "Solo2"}
    resp = api_client.post(f"/orgs/{org.slug}/contacts/", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Solo2"
    # Case 3: Only last_name (unique)
    payload = {"last_name": "Surname3"}
    resp = api_client.post(f"/orgs/{org.slug}/contacts/", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Surname3"
    # Case 4: No names at all
    payload = {}
    resp = api_client.post(f"/orgs/{org.slug}/contacts/", json=payload, headers=headers)
    assert resp.status_code == 400
    errors = resp.json()
    assert isinstance(errors, dict)
    assert "detail" in errors
    assert "at least one of display_name" in errors["detail"].lower()


@pytest.mark.django_db
def test_update_contact_fields_within_organization(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org1 = Organization.objects.create(
        name="Org1", slug="org1", type="group", creator=user
    )
    org2 = Organization.objects.create(
        name="Org2", slug="org2", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org1, role="owner")
    Membership.objects.create(user=user, organization=org2, role="owner")
    contact = Contact.objects.create(
        display_name="Original Name",
        slug="original-name",
        organization=org1,
        creator=user,
        email="old@email.com",
        phone="12345",
    )
    headers = make_auth_headers(api_client, user, password="pw")
    payload = {"display_name": "New Name", "email": "new@email.com", "phone": "67890"}
    resp = api_client.put(
        f"/orgs/{org1.slug}/contacts/{contact.slug}/", json=payload, headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "New Name"
    assert data["organization"] == org1.slug
    assert data["email"] == "new@email.com"
    assert data["phone"] == "67890"
    # Confirm DB update
    contact.refresh_from_db()
    assert contact.display_name == "New Name"
    assert contact.organization == org1
    assert contact.email == "new@email.com"
    assert contact.phone == "67890"


@pytest.mark.django_db
def test_update_contact_rejects_organization_in_body(make_auth_headers, api_client):
    user = create_test_user(
        email="move@example.com", password="pw", username="moveuser", slug="moveuser"
    )
    org1 = Organization.objects.create(
        name="Move Org1", slug="move-org1", type="group", creator=user
    )
    org2 = Organization.objects.create(
        name="Move Org2", slug="move-org2", type="group", creator=None
    )
    Membership.objects.create(user=user, organization=org1, role="owner")
    contact = Contact.objects.create(
        display_name="Move Me", slug="move-me", organization=org1, creator=user
    )
    headers = make_auth_headers(api_client, user, password="pw")

    resp = api_client.put(
        f"/orgs/{org1.slug}/contacts/{contact.slug}/",
        json={"display_name": "Move Me", "organization": org2.slug},
        headers=headers,
    )

    assert resp.status_code == 400
    contact.refresh_from_db()
    assert contact.organization == org1


@pytest.mark.django_db
def test_upload_contact_avatar_error(monkeypatch, make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org = Organization.objects.create(
        name="Avatar Org", slug="avatar-org", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org, role="owner")
    contact = Contact.objects.create(
        display_name="AvatarFail", slug="avatarfail", organization=org, creator=user
    )
    headers = make_auth_headers(api_client, user, password="pw")

    # Monkeypatch resize_avatar_images to raise Exception
    def fail_resize(*a, **kw):
        raise Exception("resize failed")

    monkeypatch.setattr("contacts.api.resize_avatar_images", fail_resize)
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.utils.datastructures import MultiValueDict

    img = Image.new("RGB", (10, 10), color="red")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    uploaded = SimpleUploadedFile(
        "fail.png", buffer.getvalue(), content_type="image/png"
    )
    files = MultiValueDict({"file": [uploaded]})
    resp = api_client.post(
        f"/orgs/{org.slug}/contacts/{contact.slug}/avatar/",
        data={},
        FILES=files,
        headers=headers,
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Avatar upload is temporarily unavailable."


@pytest.mark.django_db
def test_partial_update_rejects_organization_in_body(make_auth_headers, api_client):
    user = create_test_user(
        email="test@example.com", password="pw", username="testuser", slug="testuser"
    )
    org1 = Organization.objects.create(
        name="Org1Patch", slug="org1patch", type="group", creator=user
    )
    org2 = Organization.objects.create(
        name="Org2Patch", slug="org2patch", type="group", creator=user
    )
    Membership.objects.create(user=user, organization=org1, role="owner")
    Membership.objects.create(user=user, organization=org2, role="owner")
    contact = Contact.objects.create(
        display_name="Patch Name", slug="patch-name", organization=org1, creator=user
    )
    headers = make_auth_headers(api_client, user, password="pw")
    payload = {"organization": org2.slug}
    resp = api_client.patch(
        f"/orgs/{org1.slug}/contacts/{contact.slug}/", json=payload, headers=headers
    )
    assert resp.status_code == 400
    contact.refresh_from_db()
    assert contact.organization == org1


@pytest.mark.django_db
def test_partial_update_contact_rejects_move_to_inaccessible_organization(
    make_auth_headers, api_client
):
    user = create_test_user(
        email="patchmove@example.com",
        password="pw",
        username="patchmove",
        slug="patchmove",
    )
    org1 = Organization.objects.create(
        name="Patch Move Org1", slug="patch-move-org1", type="group", creator=user
    )
    org2 = Organization.objects.create(
        name="Patch Move Org2", slug="patch-move-org2", type="group", creator=None
    )
    Membership.objects.create(user=user, organization=org1, role="owner")
    contact = Contact.objects.create(
        display_name="Patch Move", slug="patch-move", organization=org1, creator=user
    )
    headers = make_auth_headers(api_client, user, password="pw")

    resp = api_client.patch(
        f"/orgs/{org1.slug}/contacts/{contact.slug}/",
        json={"organization": org2.slug},
        headers=headers,
    )

    assert resp.status_code == 400
    contact.refresh_from_db()
    assert contact.organization == org1
