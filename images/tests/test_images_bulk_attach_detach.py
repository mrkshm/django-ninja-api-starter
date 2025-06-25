import io
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from organizations.models import Organization, Membership
from images.models import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image as PilImage
from DjangoApiStarter.api import api  # noqa: F401 - ensure API is loaded once

def create_test_image_file(color=(100, 200, 50), size=(300, 300), name="testimg.png"):
    img = PilImage.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")

def get_access_token(email, password):
    client = Client()
    resp = client.post("/api/v1/token/pair", data={"email": email, "password": password}, content_type="application/json")
    if resp.status_code != 200 or "access" not in resp.json():
        resp2 = client.post("/api/v1/token/pair", data={"email": email, "password": password}, content_type="application/x-www-form-urlencoded")
        data = resp2.json()
        return data.get("access")
    data = resp.json()
    return data.get("access")

User = get_user_model()


@pytest.mark.django_db
def test_bulk_attach_and_detach_images_to_object():
    org = Organization.objects.create(name="BulkAttachOrg", slug="bulkattachorg")
    user = User.objects.create_user(email="bulkattach@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")

    # Create two images in same org
    img1 = Image.objects.create(file=create_test_image_file(name="ba1.png"), organization=org, creator=user)
    img2 = Image.objects.create(file=create_test_image_file(name="ba2.png"), organization=org, creator=user)

    # Use organization as target object
    app_label = "organizations"
    model = "organization"
    object_id = org.id

    client = Client()
    access = get_access_token("bulkattach@example.com", "pw")

    # Bulk attach
    attach_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{object_id}/bulk_attach/"
    resp = client.post(
        attach_url,
        data={"image_ids": [img1.id, img2.id]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    assert resp.status_code == 200, resp.content
    data = resp.json()
    # Expect BulkAttachOut { attached: number[] }
    assert "attached" in data and set(data["attached"]) == {img1.id, img2.id}

    # Bulk detach
    detach_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{object_id}/bulk_detach/"
    resp = client.post(
        detach_url,
        data={"image_ids": [img1.id, img2.id]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    assert resp.status_code == 200, resp.content
    data = resp.json()
    # Expect BulkDetachOut { detached: number[] }
    assert "detached" in data and set(data["detached"]) == {img1.id, img2.id}


@pytest.mark.django_db
def test_bulk_attach_rejects_images_from_other_org():
    org1 = Organization.objects.create(name="Org1", slug="org1")
    org2 = Organization.objects.create(name="Org2", slug="org2")
    user = User.objects.create_user(email="bulkattach2@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org1, role="owner")

    img_other = Image.objects.create(file=create_test_image_file(name="other.png"), organization=org2, creator=user)

    app_label = "organizations"
    model = "organization"
    object_id = org1.id

    client = Client()
    access = get_access_token("bulkattach2@example.com", "pw")

    attach_url = f"/api/v1/images/orgs/{org1.slug}/images/{app_label}/{model}/{object_id}/bulk_attach/"
    resp = client.post(
        attach_url,
        data={"image_ids": [img_other.id]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    # Should forbid attaching images from another org
    assert resp.status_code in (403, 404, 400)
