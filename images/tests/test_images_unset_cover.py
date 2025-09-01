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


def create_test_image_file(color=(120, 30, 60), size=(64, 64), name="t2.png"):
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
def test_unset_cover_clears_flag_without_reorder():
    org = Organization.objects.create(name="OrgU", slug="orgu")
    user = User.objects.create_user(email="u@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    imgs = [
        Image.objects.create(file=create_test_image_file(name=f"u{i}.png"), organization=org, creator=user)
        for i in range(3)
    ]

    client = Client()
    token = get_access_token("u@example.com", "pw")

    app_label = "organizations"
    model = "organization"
    obj_id = org.id

    # Attach
    attach_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/"
    client.post(attach_url, data={"image_ids": [i.id for i in imgs]}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")

    # Set a cover first
    set_cover_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/set_cover"
    client.post(set_cover_url, data={"image_id": imgs[1].id}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")

    # Capture order and then unset
    ct = ContentType.objects.get(app_label=app_label, model=model)
    before = list(PolymorphicImageRelation.objects.filter(content_type=ct, object_id=obj_id).order_by("order", "pk"))
    initial_order = [r.image_id for r in before]

    unset_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/unset_cover"
    resp = client.post(unset_url, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 200

    after = list(PolymorphicImageRelation.objects.filter(content_type=ct, object_id=obj_id).order_by("order", "pk"))
    assert [r.image_id for r in after] == initial_order
    assert all(not r.is_cover for r in after)


@pytest.mark.django_db
def test_unset_cover_idempotent():
    org = Organization.objects.create(name="OrgUI", slug="orgui")
    user = User.objects.create_user(email="ui@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    imgs = [Image.objects.create(file=create_test_image_file(name=f"i{i}.png"), organization=org, creator=user) for i in range(2)]

    client = Client()
    token = get_access_token("ui@example.com", "pw")
    app_label = "organizations"
    model = "organization"
    obj_id = org.id

    attach_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/"
    client.post(attach_url, data={"image_ids": [i.id for i in imgs]}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")

    set_cover_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/set_cover"
    client.post(set_cover_url, data={"image_id": imgs[0].id}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")

    unset_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/unset_cover"
    r1 = client.post(unset_url, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert r1.status_code == 200
    r2 = client.post(unset_url, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert r2.status_code == 200

    ct = ContentType.objects.get(app_label=app_label, model=model)
    rels = list(PolymorphicImageRelation.objects.filter(content_type=ct, object_id=obj_id))
    assert sum(1 for r in rels if r.is_cover) == 0


@pytest.mark.django_db
def test_unset_cover_auth_required():
    org = Organization.objects.create(name="OrgUA", slug="orgua")
    user = User.objects.create_user(email="ua@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    img = Image.objects.create(file=create_test_image_file(name="ua.png"), organization=org, creator=user)

    app_label = "organizations"
    model = "organization"
    obj_id = org.id

    # attach
    ct = ContentType.objects.get(app_label=app_label, model=model)
    PolymorphicImageRelation.objects.create(image=img, content_type=ct, object_id=obj_id, is_cover=True)

    unset_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/unset_cover"
    resp = Client().post(unset_url, content_type="application/json")
    assert resp.status_code in (401, 403)
