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
def test_set_cover_toggles_without_reorder():
    org = Organization.objects.create(name="OrgC", slug="orgc")
    user = User.objects.create_user(email="c@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")

    imgs = [
        Image.objects.create(file=create_test_image_file(name=f"{i}.png"), organization=org, creator=user)
        for i in range(3)
    ]

    client = Client()
    token = get_access_token("c@example.com", "pw")
    assert token

    app_label = "organizations"
    model = "organization"
    obj_id = org.id

    # Attach all images
    attach_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/"
    resp = client.post(
        attach_url,
        data={"image_ids": [i.id for i in imgs]},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert resp.status_code == 200

    # Record initial order
    ct = ContentType.objects.get(app_label=app_label, model=model)
    before = list(
        PolymorphicImageRelation.objects.filter(content_type=ct, object_id=obj_id).order_by("order", "pk")
    )
    initial_order_ids = [r.image_id for r in before]

    # Set cover to the last image
    set_cover_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/set_cover"
    target_id = imgs[-1].id
    resp = client.post(
        set_cover_url,
        data={"image_id": target_id},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert resp.status_code == 200, resp.content

    after = list(
        PolymorphicImageRelation.objects.filter(content_type=ct, object_id=obj_id).order_by("order", "pk")
    )
    # Order should be unchanged
    assert [r.image_id for r in after] == initial_order_ids
    # Exactly one cover, and it is the chosen one
    covers = [r for r in after if r.is_cover]
    assert len(covers) == 1
    assert covers[0].image_id == target_id


@pytest.mark.django_db
def test_set_cover_idempotent():
    org = Organization.objects.create(name="OrgD", slug="orgd")
    user = User.objects.create_user(email="d@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")
    imgs = [
        Image.objects.create(file=create_test_image_file(name=f"{i}.png"), organization=org, creator=user)
        for i in range(2)
    ]

    client = Client()
    token = get_access_token("d@example.com", "pw")

    app_label = "organizations"
    model = "organization"
    obj_id = org.id

    attach_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/"
    client.post(attach_url, data={"image_ids": [i.id for i in imgs]}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")

    set_cover_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/set_cover"
    target_id = imgs[0].id

    # First call
    r1 = client.post(
        set_cover_url,
        data={"image_id": target_id},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert r1.status_code == 200

    # Second call (idempotent)
    r2 = client.post(
        set_cover_url,
        data={"image_id": target_id},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert r2.status_code == 200

    ct = ContentType.objects.get(app_label=app_label, model=model)
    rels = list(PolymorphicImageRelation.objects.filter(content_type=ct, object_id=obj_id).order_by("order", "pk"))
    assert sum(1 for r in rels if r.is_cover) == 1
    assert any(r.image_id == target_id and r.is_cover for r in rels)


@pytest.mark.django_db
def test_set_cover_requires_attachment():
    org = Organization.objects.create(name="OrgE", slug="orge")
    user = User.objects.create_user(email="e@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")

    img = Image.objects.create(file=create_test_image_file(name="x.png"), organization=org, creator=user)

    client = Client()
    token = get_access_token("e@example.com", "pw")

    app_label = "organizations"
    model = "organization"
    obj_id = org.id

    # Do NOT attach, try to set cover directly -> 404
    set_cover_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/set_cover"
    resp = client.post(
        set_cover_url,
        data={"image_id": img.id},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_set_cover_wrong_org_image_404():
    org1 = Organization.objects.create(name="OrgF", slug="orgf")
    org2 = Organization.objects.create(name="OrgG", slug="orgg")
    user = User.objects.create_user(email="f@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org1, role="owner")

    # Image belongs to different org
    foreign_img = Image.objects.create(file=create_test_image_file(name="z.png"), organization=org2, creator=user)

    client = Client()
    token = get_access_token("f@example.com", "pw")

    app_label = "organizations"
    model = "organization"
    obj_id = org1.id

    set_cover_url = f"/api/v1/images/orgs/{org1.slug}/images/{app_label}/{model}/{obj_id}/set_cover"
    resp = client.post(
        set_cover_url,
        data={"image_id": foreign_img.id},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    # Image lookup is scoped to organization -> 404
    assert resp.status_code == 404


@pytest.mark.django_db
def test_set_cover_auth_required():
    org = Organization.objects.create(name="OrgH", slug="orgh")
    user = User.objects.create_user(email="h@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")

    img = Image.objects.create(file=create_test_image_file(name="h.png"), organization=org, creator=user)

    app_label = "organizations"
    model = "organization"
    obj_id = org.id

    # Try without auth token
    set_cover_url = f"/api/v1/images/orgs/{org.slug}/images/{app_label}/{model}/{obj_id}/set_cover"
    resp = Client().post(
        set_cover_url,
        data={"image_id": img.id},
        content_type="application/json",
    )
    assert resp.status_code in (401, 403)
