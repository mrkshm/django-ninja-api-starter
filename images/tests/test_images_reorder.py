import io
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image as PilImage
from django.contrib.contenttypes.models import ContentType

from organizations.models import Organization, Membership
from images.models import Image, PolymorphicImageRelation

User = get_user_model()


def create_test_image_file(color=(10, 20, 30), size=(64, 64), name="t.png"):
    img = PilImage.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")


def get_access_token(email, password):
    client = Client()
    resp = client.post(
        "/api/v1/token/pair",
        data={"email": email, "password": password},
        content_type="application/json",
    )
    if resp.status_code == 200 and "access" in resp.json():
        return resp.json().get("access")
    # fallback
    resp2 = client.post(
        "/api/v1/token/pair",
        data={"email": email, "password": password},
        content_type="application/x-www-form-urlencoded",
    )
    return resp2.json().get("access")


@pytest.mark.django_db
def test_attach_defaults_primary_and_order():
    org = Organization.objects.create(name="OrgA", slug="orga")
    user = User.objects.create_user(email="a@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")

    img1 = Image.objects.create(file=create_test_image_file(name="a.png"), organization=org, creator=user)
    img2 = Image.objects.create(file=create_test_image_file(name="b.png"), organization=org, creator=user)

    client = Client()
    token = get_access_token("a@example.com", "pw")
    assert token

    app_label = "organizations"
    model = "organization"
    obj_id = org.id

    # attach both
    url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/"
    resp = client.post(url, data={"image_ids": [img1.id]}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 200
    resp = client.post(url, data={"image_ids": [img2.id]}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 200

    ct = ContentType.objects.get(app_label=app_label, model=model)
    rels = list(PolymorphicImageRelation.objects.filter(content_type=ct, object_id=obj_id).order_by("order", "pk"))
    assert len(rels) == 2
    assert rels[0].image_id == img1.id
    assert rels[0].is_cover is True
    assert rels[0].order == 0
    assert rels[1].image_id == img2.id
    assert rels[1].is_cover is False
    assert rels[1].order == 1


@pytest.mark.django_db
def test_reorder_sets_primary_and_orders():
    org = Organization.objects.create(name="OrgB", slug="orgb")
    user = User.objects.create_user(email="b@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")

    imgs = [Image.objects.create(file=create_test_image_file(name=f"{i}.png"), organization=org, creator=user) for i in range(3)]

    client = Client()
    token = get_access_token("b@example.com", "pw")
    assert token

    app_label = "organizations"
    model = "organization"
    obj_id = org.id

    attach_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/"
    resp = client.post(attach_url, data={"image_ids": [i.id for i in imgs]}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 200

    # reorder to [2, 0, 1]
    new_order = [imgs[2].id, imgs[0].id, imgs[1].id]
    reorder_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/reorder"
    resp = client.post(reorder_url, data={"image_ids": new_order}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 200

    ct = ContentType.objects.get(app_label=app_label, model=model)
    rels = list(PolymorphicImageRelation.objects.filter(content_type=ct, object_id=obj_id).order_by("order", "pk"))
    assert [r.image_id for r in rels] == new_order
    assert rels[0].is_cover is True
    assert all(not r.is_cover for r in rels[1:])
