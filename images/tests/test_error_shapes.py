import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from organizations.models import Organization, Membership
from DjangoApiStarter.api import api  # ensure API loads
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()


@pytest.mark.django_db
def test_invalid_upload_error_shape():
    org = Organization.objects.create(name="ErrOrg", slug="errorg")
    user = User.objects.create_user(email="err@example.com", password="pw", email_verified=True)
    Membership.objects.create(user=user, organization=org, role="owner")

    client = Client()
    # get token
    resp = client.post("/api/v1/token/pair", data={"email": "err@example.com", "password": "pw"}, content_type="application/json")
    access = resp.json()["access"]

    bad_file = SimpleUploadedFile("notimage.txt", b"not an image", content_type="text/plain")
    response = client.post(
        f"/api/v1/images/orgs/{org.slug}/images/",
        {"file": bad_file},
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    assert response.status_code == 400
    data = response.json()
    assert isinstance(data, dict)
    assert "detail" in data
    assert isinstance(data["detail"], str)
