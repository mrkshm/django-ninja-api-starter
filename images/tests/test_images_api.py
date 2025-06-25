import pytest
from django.contrib.auth import get_user_model
from organizations.models import Organization, Membership
from images.models import Image
from DjangoApiStarter.api import api
from django.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile
import io
from PIL import Image as PilImage
from django.contrib.contenttypes.models import ContentType
from accounts.tests.utils import create_test_user

User = get_user_model()

# Helper to create test image file
def create_test_image_file(color=(100, 200, 50), size=(300, 300), name="testimg.png"):
    img = PilImage.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")

# Helper to get JWT access token
def get_access_token(email, password):
    client = Client()
    # Try both data and json, log the response for debugging
    resp = client.post("/api/v1/token/pair", data={"email": email, "password": password}, content_type="application/json")
    if resp.status_code != 200 or "access" not in resp.json():
        print("Token endpoint response (json):", resp.status_code, resp.content)
        # Try as form-urlencoded fallback
        resp2 = client.post("/api/v1/token/pair", data={"email": email, "password": password}, content_type="application/x-www-form-urlencoded")
        print("Token endpoint response (form):", resp2.status_code, resp2.content)
        data = resp2.json()
        return data.get("access")
    data = resp.json()
    return data.get("access")

@pytest.mark.django_db
def test_list_images_for_org():
    org = Organization.objects.create(name="TestOrg", slug="testorg")
    user = User.objects.create_user(email="imgtest@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    img1 = Image.objects.create(
        file=create_test_image_file(name="test1.png"), organization=org, creator=user, description="desc1", title="img1", alt_text="alt1"
    )
    img2 = Image.objects.create(
        file=create_test_image_file(name="test2.png"), organization=org, creator=user, description="desc2", title="img2", alt_text="alt2"
    )
    client = Client()
    access = get_access_token("imgtest@example.com", "pw")
    assert access, "Failed to get access token. Check credentials and token endpoint."
    url = f"/api/v1/images/orgs/{org.slug}/images/"
    response = client.get(url, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["count"] == 2
    ids = {item["id"] for item in data["items"]}
    assert img1.id in ids and img2.id in ids

@pytest.mark.django_db
def test_upload_image():
    org = Organization.objects.create(name="UploadOrg", slug="uploadorg")
    user = User.objects.create_user(email="upload@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    client = Client()
    access = get_access_token("upload@example.com", "pw")
    assert access, "Failed to get access token. Check credentials and token endpoint."
    file = create_test_image_file(name="upload.png")
    response = client.post(
        f"/api/v1/images/orgs/{org.slug}/images/",
        {"file": file},
        HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert response.status_code == 200, response.content
    data = response.json()
    assert "id" in data
    assert data["file"].endswith(".png") or data["file"].endswith(".webp")

@pytest.mark.django_db
def test_bulk_upload_images():
    org = Organization.objects.create(name="BulkOrg", slug="bulkorg")
    user = User.objects.create_user(email="bulk@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    client = Client()
    access = get_access_token("bulk@example.com", "pw")
    assert access, "Failed to get access token. Check credentials and token endpoint."
    files = [create_test_image_file(name=f"bulk{i}.png") for i in range(3)]
    files_dict = {"files": files}
    response = client.post(
        f"/api/v1/images/orgs/{org.slug}/bulk-upload/",
        files_dict,
        HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert response.status_code == 200, response.content
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3
    for item in data:
        assert item["status"] == "success"
        assert "file" in item

@pytest.mark.django_db
def test_delete_image():
    org = Organization.objects.create(name="DelOrg", slug="delorg")
    user = User.objects.create_user(email="delete@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    img = Image.objects.create(
        file=create_test_image_file(name="del.png"), organization=org, creator=user
    )
    client = Client()
    access = get_access_token("delete@example.com", "pw")
    assert access, "Failed to get access token. Check credentials and token endpoint."
    response = client.delete(f"/api/v1/images/orgs/{org.slug}/images/{img.id}/", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code == 204
    assert not Image.objects.filter(id=img.id).exists()

@pytest.mark.django_db
def test_bulk_delete_images():
    org = Organization.objects.create(name="BulkDelOrg", slug="bulkdelorg")
    user = User.objects.create_user(email="bulkdel@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    imgs = [Image.objects.create(file=create_test_image_file(name=f"bd{i}.png"), organization=org, creator=user) for i in range(2)]
    client = Client()
    access = get_access_token("bulkdel@example.com", "pw")
    assert access, "Failed to get access token. Check credentials and token endpoint."
    ids = [img.id for img in imgs]
    response = client.post(
        f"/api/v1/images/orgs/{org.slug}/bulk-delete/",
        {"ids": ids},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert response.status_code == 204, response.content
    for img_id in ids:
        assert not Image.objects.filter(id=img_id).exists()

@pytest.mark.django_db
def test_attach_and_detach_image():
    # Create org and user
    org = Organization.objects.create(name="AttachOrg", slug="attachorg")
    user = User.objects.create_user(email="attach@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    img = Image.objects.create(file=create_test_image_file(name="att.png"), organization=org, creator=user)

    # Use organization as the target object for polymorphic relation
    app_label = "organizations"
    model = "organization"
    object_id = org.id

    client = Client()
    access = get_access_token("attach@example.com", "pw")
    assert access, "Failed to get access token. Check credentials and token endpoint."

    # Attach via polymorphic endpoint
    attach_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{object_id}/"
    response = client.post(
        attach_url,
        data={"image_ids": [img.id]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert response.status_code == 200, response.content

    # Detach via DELETE (204 No Content)
    detach_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{object_id}/{img.id}/"
    response = client.delete(detach_url, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code == 204, response.content

@pytest.mark.django_db
def test_list_images_for_object():
    org = Organization.objects.create(name="ObjOrg", slug="objorg")
    user = User.objects.create_user(email="objuser@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    img = Image.objects.create(file=create_test_image_file(name="objimg.png"), organization=org, creator=user)
    # Attach image to org as content object
    app_label = "organizations"
    model = "organization"
    object_id = org.id
    ct = ContentType.objects.get(app_label=app_label, model=model)
    from images.models import PolymorphicImageRelation
    PolymorphicImageRelation.objects.create(image=img, content_type=ct, object_id=object_id)

    client = Client()
    access = get_access_token("objuser@example.com", "pw")
    url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{object_id}/"
    response = client.get(url, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["count"] == 1
    assert data["items"][0]["image"]["id"] == img.id

    # 403 if object belongs to another org
    org2 = Organization.objects.create(name="OtherOrg", slug="otherorg")
    object_id2 = org2.id
    response = client.get(f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{object_id2}/", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code == 403

    # 404 if object does not exist
    response = client.get(f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/999999/", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code == 404

@pytest.mark.django_db
def test_unauthorized_access():
    org = Organization.objects.create(name="NoAuthOrg", slug="noauthorg")
    user = User.objects.create_user(email="noauth@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    img = Image.objects.create(file=create_test_image_file(name="noauth.png"), organization=org, creator=user)
    # No login_client here
    client = Client()
    url = f"/api/v1/images/orgs/{org.slug}/images/"
    response = client.get(url)
    assert response.status_code in (401, 403)
    response = client.post(f"/api/v1/images/orgs/{org.slug}/images/", files={"file": create_test_image_file(name="fail.png")})
    assert response.status_code in (401, 403)
    response = client.delete(f"/api/v1/images/orgs/{org.slug}/images/{img.id}/")
    assert response.status_code in (401, 403)

@pytest.mark.django_db
def test_upload_invalid_file():
    org = Organization.objects.create(name="InvalidOrg", slug="invalidorg")
    user = User.objects.create_user(email="invalid@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    client = Client()
    access = get_access_token("invalid@example.com", "pw")
    assert access, "Failed to get access token. Check credentials and token endpoint."
    bad_file = SimpleUploadedFile("notimage.txt", b"not an image", content_type="text/plain")
    response = client.post(
        f"/api/v1/images/orgs/{org.slug}/images/",
        {"file": bad_file},
        HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert response.status_code == 400

@pytest.mark.django_db
def test_attach_images_to_object():
    org = Organization.objects.create(name="AttachOrg", slug="attachorg")
    user = User.objects.create_user(email="attach@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    img = Image.objects.create(file=create_test_image_file(name="attachimg.png"), organization=org, creator=user)
    app_label = "organizations"
    model = "organization"
    object_id = org.id
    client = Client()
    access = get_access_token("attach@example.com", "pw")
    assert access, "Failed to get access token. Check credentials and token endpoint."
    url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{object_id}/"
    response = client.post(url, data={"image_ids": [img.id]}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code == 200
    data = response.json()
    assert any(r["image"]["id"] == img.id for r in data) or any(r["image"] == img.id for r in data)

    org2 = Organization.objects.create(name="OtherOrg", slug="otherorg")
    img2 = Image.objects.create(file=create_test_image_file(name="failimg.png"), organization=org2, creator=user)
    response = client.post(url, data={"image_ids": [img2.id]}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code in (403, 404)

@pytest.mark.django_db
def test_remove_image_from_object():
    org = Organization.objects.create(name="RemoveOrg", slug="removeorg")
    user = User.objects.create_user(email="remove@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    img = Image.objects.create(file=create_test_image_file(name="removeimg.png"), organization=org, creator=user)
    app_label = "organizations"
    model = "organization"
    object_id = org.id
    # Attach image to org as content object
    from images.models import PolymorphicImageRelation
    ct = ContentType.objects.get(app_label=app_label, model=model)
    PolymorphicImageRelation.objects.create(image=img, content_type=ct, object_id=object_id)
    client = Client()
    access = get_access_token("remove@example.com", "pw")
    assert access, "Failed to get access token. Check credentials and token endpoint."
    url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{object_id}/{img.id}/"
    response = client.delete(url, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code == 200 or response.status_code == 204
    # Relation should be gone
    assert not PolymorphicImageRelation.objects.filter(image=img, content_type=ct, object_id=object_id).exists()
    # Should 404 if relation does not exist
    response = client.delete(url, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert response.status_code in (404, 400)
