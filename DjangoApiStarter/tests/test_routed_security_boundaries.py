import io
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from ninja_jwt.tokens import AccessToken
from PIL import Image as PillowImage

from accounts.models import AuthSession
from accounts.services import issue_token_pair
from contacts.models import Contact
from images.models import Image
from organizations.models import Membership, Organization
from organizations.tests.utils import create_test_group
from tags.models import Tag

User = get_user_model()


def headers_for(user):
    access, _refresh = issue_token_pair(user)
    return {"Authorization": f"Bearer {access}"}


def image_upload(*, name: str = "image.png", color: str = "blue"):
    buffer = io.BytesIO()
    PillowImage.new("RGB", (16, 16), color=color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def assert_authentication_rejected(response):
    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.fixture
def routed_tenant():
    owner = User.objects.create_user(email="route-owner@example.com", password="pw")
    admin = User.objects.create_user(email="route-admin@example.com", password="pw")
    member = User.objects.create_user(email="route-member@example.com", password="pw")
    outsider = User.objects.create_user(
        email="route-outsider@example.com", password="pw"
    )
    organization = Organization.objects.create(
        name="Routed", slug="routed", type="group"
    )
    Membership.objects.create(user=owner, organization=organization, role="owner")
    Membership.objects.create(user=admin, organization=organization, role="admin")
    Membership.objects.create(user=member, organization=organization, role="member")
    contact = Contact.objects.create(
        display_name="Routed Contact",
        slug="routed-contact",
        organization=organization,
        creator=owner,
    )
    Tag.objects.create(organization=organization, name="Routed", slug="routed")
    Image.objects.create(
        organization=organization,
        creator=owner,
        file="private/images/routed.webp",
    )
    return organization, contact, owner, admin, member, outsider


@pytest.mark.django_db
def test_route_families_hide_unknown_and_inaccessible_tenants(
    api_client,
    routed_tenant,
):
    organization, _contact, _owner, _admin, _member, outsider = routed_tenant
    headers = headers_for(outsider)
    path_templates = [
        "/orgs/{slug}/contacts/",
        "/orgs/{slug}/tags/",
        "/orgs/{slug}/images/",
        "/orgs/{slug}/exports/",
    ]

    for template in path_templates:
        inaccessible = api_client.get(
            template.format(slug=organization.slug), headers=headers
        )
        unknown = api_client.get(
            template.format(slug="does-not-exist"), headers=headers
        )
        assert inaccessible.status_code == unknown.status_code == 404
        assert (
            inaccessible.json()
            == unknown.json()
            == {"detail": "Organization not found"}
        )


@pytest.mark.django_db
def test_routed_roles_enforce_member_and_admin_boundaries(api_client, routed_tenant):
    organization, _contact, owner, admin, member, _outsider = routed_tenant
    ordinary_paths = [
        f"/orgs/{organization.slug}/contacts/",
        f"/orgs/{organization.slug}/tags/",
        f"/orgs/{organization.slug}/images/",
    ]
    for user in (owner, admin, member):
        for path in ordinary_paths:
            assert api_client.get(path, headers=headers_for(user)).status_code == 200

    export_path = f"/orgs/{organization.slug}/exports/"
    assert api_client.get(export_path, headers=headers_for(owner)).status_code == 200
    assert api_client.get(export_path, headers=headers_for(admin)).status_code == 200
    member_response = api_client.get(export_path, headers=headers_for(member))
    assert member_response.status_code == 403


@pytest.mark.django_db
def test_protected_route_rejects_the_full_invalid_jwt_matrix(api_client):
    path = "/users/me"
    user = User.objects.create_user(email="jwt-matrix@example.com", password="pw")
    access, _refresh = issue_token_pair(user)

    assert_authentication_rejected(api_client.get(path))
    assert_authentication_rejected(
        api_client.get(path, headers={"Authorization": "Bearer not-a-jwt"})
    )

    expired = AccessToken(access)
    expired.set_exp(
        from_time=timezone.now() - timedelta(minutes=5),
        lifetime=timedelta(seconds=1),
    )
    assert_authentication_rejected(
        api_client.get(path, headers={"Authorization": f"Bearer {expired}"})
    )

    session = AuthSession.objects.get(user=user)
    session.revoke()
    assert_authentication_rejected(
        api_client.get(path, headers={"Authorization": f"Bearer {access}"})
    )

    stale_access, _refresh = issue_token_pair(user)
    User.objects.filter(pk=user.pk).update(auth_version=user.auth_version + 1)
    assert_authentication_rejected(
        api_client.get(path, headers={"Authorization": f"Bearer {stale_access}"})
    )

    user.refresh_from_db()
    inactive_access, _refresh = issue_token_pair(user)
    User.objects.filter(pk=user.pk).update(is_active=False)
    assert_authentication_rejected(
        api_client.get(path, headers={"Authorization": f"Bearer {inactive_access}"})
    )


@pytest.mark.django_db
def test_platform_admin_cross_tenant_flow_is_routed_and_audited(api_client):
    organization = create_test_group(name="Platform Scope", slug="platform-scope")
    superuser = User.objects.create_superuser(
        email="routed-platform-admin@example.com", password="pw"
    )
    staff = User.objects.create_user(
        email="routed-staff@example.com",
        password="pw",
        is_staff=True,
    )
    list_path = f"/orgs/{organization.slug}/contacts/"

    with patch("organizations.scope.audit_logger.info") as audit_info:
        listed = api_client.get(list_path, headers=headers_for(superuser))
        created = api_client.post(
            list_path,
            json={"display_name": "Created by platform admin"},
            headers=headers_for(superuser),
        )

    assert listed.status_code == 200
    assert created.status_code == 201
    assert audit_info.call_count == 2
    assert all(
        call.kwargs["extra"]["event"] == "platform_admin_tenant_access"
        and call.kwargs["extra"]["org"] == organization.pk
        and call.kwargs["extra"]["user"] == superuser.pk
        for call in audit_info.call_args_list
    )

    inaccessible = api_client.get(list_path, headers=headers_for(staff))
    unknown = api_client.get(
        "/orgs/unknown-platform-scope/contacts/", headers=headers_for(staff)
    )
    assert inaccessible.status_code == unknown.status_code == 404
    assert inaccessible.json() == unknown.json() == {"detail": "Organization not found"}


@pytest.mark.django_db
def test_json_idempotency_runs_through_router(api_client, routed_tenant):
    organization, contact, owner, _admin, _member, _outsider = routed_tenant
    first = Image.objects.create(
        organization=organization, creator=owner, file="private/images/first.webp"
    )
    second = Image.objects.create(
        organization=organization, creator=owner, file="private/images/second.webp"
    )
    path = (
        f"/orgs/{organization.slug}/images/contacts/contact/{contact.pk}/"
        "bulk_attach/"
    )
    headers = {**headers_for(owner), "Idempotency-Key": "routed-json-key"}

    initial = api_client.post(path, json={"image_ids": [first.pk]}, headers=headers)
    replay = api_client.post(path, json={"image_ids": [first.pk]}, headers=headers)
    conflict = api_client.post(path, json={"image_ids": [second.pk]}, headers=headers)

    assert initial.status_code == replay.status_code == 200
    assert initial.json() == replay.json()
    assert conflict.status_code == 409


@pytest.mark.django_db
def test_multipart_idempotency_hashes_real_file_bytes(api_client, routed_tenant):
    organization, _contact, owner, _admin, _member, _outsider = routed_tenant
    path = f"/orgs/{organization.slug}/bulk-upload/"
    headers = {**headers_for(owner), "Idempotency-Key": "routed-file-key"}

    initial = api_client.post(
        path,
        data={},
        FILES={"files": [image_upload(color="blue")]},
        headers=headers,
    )
    replay = api_client.post(
        path,
        data={},
        FILES={"files": [image_upload(color="blue")]},
        headers=headers,
    )
    conflict = api_client.post(
        path,
        data={},
        FILES={"files": [image_upload(color="red")]},
        headers=headers,
    )

    assert initial.status_code == replay.status_code == 200
    assert initial.json() == replay.json()
    assert conflict.status_code == 409


@pytest.mark.django_db
def test_distinct_idempotency_keys_execute_bulk_uploads_independently(
    api_client, routed_tenant
):
    organization, _contact, owner, _admin, _member, _outsider = routed_tenant
    path = f"/orgs/{organization.slug}/bulk-upload/"

    first = api_client.post(
        path,
        data={},
        FILES={"files": [image_upload(name="first.png")]},
        headers={**headers_for(owner), "Idempotency-Key": "upload-first"},
    )
    second = api_client.post(
        path,
        data={},
        FILES={"files": [image_upload(name="second.png")]},
        headers={**headers_for(owner), "Idempotency-Key": "upload-second"},
    )

    assert first.status_code == second.status_code == 200
    assert first.json()[0]["id"] != second.json()[0]["id"]


@pytest.mark.django_db
def test_bulk_detach_replay_runs_through_router(api_client, routed_tenant):
    organization, contact, owner, _admin, _member, _outsider = routed_tenant
    image = Image.objects.create(
        organization=organization,
        creator=owner,
        file="private/images/detach.webp",
    )
    base_path = f"/orgs/{organization.slug}/images/contacts/contact/{contact.pk}"
    auth_headers = headers_for(owner)
    attached = api_client.post(
        f"{base_path}/bulk_attach/",
        json={"image_ids": [image.pk]},
        headers=auth_headers,
    )
    headers = {**auth_headers, "Idempotency-Key": "routed-detach-key"}

    initial = api_client.post(
        f"{base_path}/bulk_detach/",
        json={"image_ids": [image.pk]},
        headers=headers,
    )
    replay = api_client.post(
        f"{base_path}/bulk_detach/",
        json={"image_ids": [image.pk]},
        headers=headers,
    )

    assert attached.status_code == 200
    assert initial.status_code == replay.status_code == 200
    assert initial.json() == replay.json() == {"detached": [image.pk]}


@pytest.mark.django_db
def test_bulk_delete_success_and_partial_failure_replay_through_router(
    api_client, routed_tenant
):
    organization, _contact, owner, _admin, _member, _outsider = routed_tenant
    success = Image.objects.create(
        organization=organization,
        creator=owner,
        file="private/images/delete-success.webp",
    )
    partial = Image.objects.create(
        organization=organization,
        creator=owner,
        file="private/images/delete-partial.webp",
    )
    path = f"/orgs/{organization.slug}/bulk-delete/"
    auth_headers = headers_for(owner)

    success_headers = {
        **auth_headers,
        "Idempotency-Key": "routed-delete-success",
    }
    initial_success = api_client.post(
        path, json={"ids": [success.pk]}, headers=success_headers
    )
    replayed_success = api_client.post(
        path, json={"ids": [success.pk]}, headers=success_headers
    )
    assert initial_success.status_code == replayed_success.status_code == 204
    assert not Image.objects.filter(pk=success.pk).exists()

    missing_id = partial.pk + 100_000
    partial_headers = {
        **auth_headers,
        "Idempotency-Key": "routed-delete-partial",
    }
    initial_partial = api_client.post(
        path,
        json={"ids": [partial.pk, missing_id]},
        headers=partial_headers,
    )
    replayed_partial = api_client.post(
        path,
        json={"ids": [partial.pk, missing_id]},
        headers=partial_headers,
    )

    assert initial_partial.status_code == replayed_partial.status_code == 400
    assert initial_partial.json() == replayed_partial.json()
    assert initial_partial.json()["deleted"] == [partial.pk]
    assert initial_partial.json()["failed"] == [
        {"id": missing_id, "reason": "not found"}
    ]
    assert not Image.objects.filter(pk=partial.pk).exists()
