import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from organizations.models import Organization, Membership
from tags.models import Tag
from DjangoApiStarter.api import api  # ensure API loads

User = get_user_model()


@pytest.mark.django_db
def test_update_tag_duplicate_name_error_shape():
    org = Organization.objects.create(name="TagErrOrg", slug="tagerrorg")
    user = User.objects.create_user(email="tagerr@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")

    # Create two tags; we'll try to rename t1 to t2's name
    t1 = Tag.objects.create(organization=org, name="alpha", slug="alpha")
    t2 = Tag.objects.create(organization=org, name="beta", slug="beta")

    client = Client()
    resp = client.post("/api/v1/token/pair", data={"email": "tagerr@example.com", "password": "pw"}, content_type="application/json")
    access = resp.json()["access"]

    resp2 = client.patch(
        f"/api/v1/orgs/{org.slug}/tags/{t1.id}/",
        data={"name": "beta"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    assert resp2.status_code == 400
    data = resp2.json()
    assert isinstance(data, dict)
    assert "detail" in data
    assert isinstance(data["detail"], str)
