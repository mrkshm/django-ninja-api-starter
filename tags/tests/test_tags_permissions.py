import io
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from organizations.models import Organization, Membership
from DjangoApiStarter.api import api  # ensure API loads
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image as PilImage

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    from django.core.cache import cache
    cache.clear()


def get_access_token(email, password):
    client = Client()
    resp = client.post(
        "/api/v1/token/pair",
        data={"email": email, "password": password},
        content_type="application/json",
    )
    if resp.status_code != 200 or "access" not in resp.json():
        resp2 = client.post(
            "/api/v1/token/pair",
            data={"email": email, "password": password},
            content_type="application/x-www-form-urlencoded",
        )
        return resp2.json().get("access")
    return resp.json().get("access")


@pytest.mark.django_db
def test_list_tags_requires_membership():
    # org exists but user is not a member
    org = Organization.objects.create(name="TagsOrg", slug="tagsorg")
    user = User.objects.create_user(email="tags1@example.com", password="pw", email_verified=True)
    client = Client()
    access = get_access_token("tags1@example.com", "pw")
    resp = client.get(f"/api/v1/orgs/{org.slug}/tags/", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_assign_tags_wrong_object_org_forbidden():
    # User is member of org1, but tries to assign tags to an object belonging to org2
    org1 = Organization.objects.create(name="OrgA", slug="orga")
    org2 = Organization.objects.create(name="OrgB", slug="orgb")
    user = User.objects.create_user(email="tags2@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org1, role="owner")

    client = Client()
    access = get_access_token("tags2@example.com", "pw")
    app_label = "organizations"
    model = "organization"
    object_id = org2.id  # object belongs to different org than route

    url = f"/api/v1/orgs/{org1.slug}/tags/{app_label}/{model}/{object_id}/"
    resp = client.post(url, data=["vip"], content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_unassign_by_slug_wrong_object_forbidden():
    org1 = Organization.objects.create(name="Org1", slug="org1tags")
    org2 = Organization.objects.create(name="Org2", slug="org2tags")
    user = User.objects.create_user(email="tags3@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org1, role="owner")

    client = Client()
    access = get_access_token("tags3@example.com", "pw")
    app_label = "organizations"
    model = "organization"
    # try to unassign from an object in a different org
    url = f"/api/v1/orgs/{org1.slug}/tags/{app_label}/{model}/{org2.id}/some-slug/"
    resp = client.delete(url, HTTP_AUTHORIZATION=f"Bearer {access}")
    assert resp.status_code == 403
