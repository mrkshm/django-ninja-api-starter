import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from images.models import Image, ImageShareLink, hash_share_token
from organizations.models import Membership, Organization


def get_access_token(email, password):
    client = Client()
    response = client.post(
        "/api/v1/token/pair",
        data={"email": email, "password": password},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    return response.json()["access"]


@pytest.mark.django_db
def test_org_member_can_get_signed_image_urls(monkeypatch):
    calls = []

    def fake_presign(key, **kwargs):
        calls.append((key, kwargs))
        return f"https://r2.example/{key}?signed=1"

    monkeypatch.setattr(
        "images.services.generate_private_presigned_storage_url", fake_presign
    )

    User = get_user_model()
    user = User.objects.create_user(
        email="signed@example.com", password="pw", email_verified=True
    )
    org = Organization.objects.create(name="Signed URL Org", slug="signed-url-org")
    Membership.objects.create(user=user, organization=org, role="owner")
    image = Image.objects.create(
        file="images/example.jpg", organization=org, creator=user
    )

    access = get_access_token("signed@example.com", "pw")
    response = Client().get(
        f"/api/v1/orgs/{org.slug}/images/{image.id}/urls",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )

    assert response.status_code == 200, response.content
    data = response.json()
    assert data["image_id"] == image.id
    assert set(data["urls"]) == {"original", "thumb", "sm", "md", "lg"}
    assert data["urls"]["original"] == "https://r2.example/images/example.jpg?signed=1"
    assert (
        "images/example_thumb.webp",
        {
            "expires_in": 900,
            "content_type": "image/webp",
            "cache_control": "private, max-age=900",
        },
    ) in calls


@pytest.mark.django_db
def test_non_member_cannot_get_signed_image_urls(monkeypatch):
    monkeypatch.setattr(
        "images.services.generate_private_presigned_storage_url",
        lambda *args, **kwargs: "unused",
    )

    User = get_user_model()
    owner = User.objects.create_user(
        email="owner@example.com", password="pw", email_verified=True
    )
    outsider = User.objects.create_user(
        email="outsider@example.com", password="pw", email_verified=True
    )
    org = Organization.objects.create(name="Private", slug="private")
    Membership.objects.create(user=owner, organization=org, role="owner")
    image = Image.objects.create(
        file="images/private.jpg", organization=org, creator=owner
    )

    access = get_access_token("outsider@example.com", "pw")
    response = Client().get(
        f"/api/v1/orgs/{org.slug}/images/{image.id}/urls",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_org_member_can_create_and_revoke_share_link(monkeypatch):
    monkeypatch.setattr(
        "images.services.generate_private_presigned_storage_url",
        lambda key, **kwargs: f"https://r2.example/{key}",
    )

    User = get_user_model()
    user = User.objects.create_user(
        email="share@example.com", password="pw", email_verified=True
    )
    org = Organization.objects.create(name="Share URL Org", slug="share-url-org")
    Membership.objects.create(user=user, organization=org, role="owner")
    image = Image.objects.create(
        file="images/share.jpg", organization=org, creator=user
    )

    access = get_access_token("share@example.com", "pw")
    client = Client()
    create_response = client.post(
        f"/api/v1/orgs/{org.slug}/images/{image.id}/shares",
        data={"expires_in_seconds": 600},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    assert create_response.status_code == 200, create_response.content
    share_data = create_response.json()
    assert share_data["image_id"] == image.id
    assert share_data["token"]
    stored_link = ImageShareLink.objects.get(pk=share_data["id"])
    assert stored_link.token_hash == hash_share_token(share_data["token"])
    assert share_data["token"] not in stored_link.token_hash

    shared_response = client.post(
        "/api/v1/shared/images/resolve/",
        data={"token": share_data["token"]},
        content_type="application/json",
    )
    assert shared_response.status_code == 200, shared_response.content
    assert (
        shared_response.json()["urls"]["original"]
        == "https://r2.example/images/share.jpg"
    )

    revoke_response = client.delete(
        f"/api/v1/orgs/{org.slug}/images/{image.id}/shares/{share_data['id']}",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    assert revoke_response.status_code == 200, revoke_response.content

    shared_response = client.post(
        "/api/v1/shared/images/resolve/",
        data={"token": share_data["token"]},
        content_type="application/json",
    )
    assert shared_response.status_code == 404


@pytest.mark.django_db
def test_expired_share_link_cannot_get_signed_urls(monkeypatch):
    monkeypatch.setattr(
        "images.services.generate_private_presigned_storage_url",
        lambda *args, **kwargs: "unused",
    )

    org = Organization.objects.create(name="Expired", slug="expired")
    image = Image.objects.create(file="images/expired.jpg", organization=org)
    share_link = ImageShareLink.objects.create(
        image=image,
        token_hash=hash_share_token("expired-share-token-value"),
        expires_at=timezone.now() - timezone.timedelta(seconds=1),
    )

    response = Client().post(
        "/api/v1/shared/images/resolve/",
        data={"token": "expired-share-token-value"},
        content_type="application/json",
    )

    assert response.status_code == 404
