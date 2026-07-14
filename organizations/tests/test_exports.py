from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from organizations.export_tasks import cleanup_expired_exports
from organizations.models import ExportJob, Membership, Organization


@pytest.mark.django_db
def test_only_org_admins_can_create_exports(api_client, make_auth_headers):
    User = get_user_model()
    admin = User.objects.create_user(email="export-admin@example.com", password="pw")
    member = User.objects.create_user(email="export-member@example.com", password="pw")
    org = Organization.objects.create(name="Export", slug="export-org", type="group")
    Membership.objects.create(user=admin, organization=org, role="admin")
    Membership.objects.create(user=member, organization=org, role="member")

    member_headers = make_auth_headers(api_client, member, password="pw")
    denied = api_client.post(f"/orgs/{org.slug}/exports/", headers=member_headers)
    assert denied.status_code == 403

    admin_headers = make_auth_headers(api_client, admin, password="pw")
    with patch("organizations.api_export.export_org_data_task.delay") as publish:
        response = api_client.post(f"/orgs/{org.slug}/exports/", headers=admin_headers)
    assert response.status_code == 202
    job = ExportJob.objects.get(pk=response.json()["id"])
    assert job.requested_by == admin
    publish.assert_called_once_with(str(job.pk))


@pytest.mark.django_db
def test_ready_export_url_is_generated_on_authenticated_read(
    api_client, make_auth_headers, monkeypatch
):
    User = get_user_model()
    admin = User.objects.create_user(email="export-read@example.com", password="pw")
    org = Organization.objects.create(
        name="Export Read", slug="export-read", type="group"
    )
    Membership.objects.create(user=admin, organization=org, role="owner")
    job = ExportJob.objects.create(
        organization=org,
        requested_by=admin,
        status=ExportJob.Status.READY,
        object_key="private/exports/1/job.zip",
        completed_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    monkeypatch.setattr(
        "organizations.api_export.generate_private_presigned_storage_url",
        lambda key, **kwargs: f"https://storage.example/{key}?signed=1",
    )

    headers = make_auth_headers(api_client, admin, password="pw")
    response = api_client.get(f"/orgs/{org.slug}/exports/{job.pk}/", headers=headers)

    assert response.status_code == 200
    assert response.json()["download_url"].endswith("?signed=1")


@pytest.mark.django_db
def test_expired_export_cleanup_removes_object(settings, monkeypatch):
    org = Organization.objects.create(name="Expired Export", slug="expired-export")
    job = ExportJob.objects.create(
        organization=org,
        status=ExportJob.Status.READY,
        object_key="private/exports/expired.zip",
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    deleted = []
    monkeypatch.setattr(
        "organizations.export_tasks.default_storage.delete", deleted.append
    )

    assert cleanup_expired_exports() == 1
    job.refresh_from_db()
    assert job.status == ExportJob.Status.EXPIRED
    assert job.object_key == ""
    assert deleted == ["private/exports/expired.zip"]
