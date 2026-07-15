from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from organizations.export_tasks import (
    cleanup_expired_exports,
    export_org_data_task,
    recover_stale_exports,
)
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
    with patch("organizations.export_tasks.export_org_data_task.delay") as publish:
        response = api_client.post(f"/orgs/{org.slug}/exports/", headers=admin_headers)
    assert response.status_code == 202
    job = ExportJob.objects.get(pk=response.json()["id"])
    assert job.requested_by == admin
    assert job.queued_at is not None
    publish.assert_called_once_with(str(job.pk))


@pytest.mark.django_db
def test_processing_export_redelivery_replaces_the_deterministic_object(monkeypatch):
    org = Organization.objects.create(name="Resume Export", slug="resume-export")
    job = ExportJob.objects.create(
        organization=org,
        status=ExportJob.Status.PROCESSING,
        object_key="private/exports/old.zip",
        started_at=timezone.now() - timedelta(minutes=10),
        heartbeat_at=timezone.now() - timedelta(minutes=10),
        attempt_count=1,
    )
    deleted = []
    monkeypatch.setattr(
        "organizations.export_tasks.build_export_archive",
        lambda _job, destination, heartbeat: destination.write(b"archive"),
    )
    monkeypatch.setattr(
        "organizations.export_tasks.default_storage.delete", deleted.append
    )
    monkeypatch.setattr(
        "organizations.export_tasks.default_storage.save", lambda name, _file: name
    )

    assert export_org_data_task.run(str(job.pk)) == str(job.pk)

    job.refresh_from_db()
    expected_key = f"private/exports/{org.pk}/{job.pk}.zip"
    assert job.status == ExportJob.Status.READY
    assert job.object_key == expected_key
    assert job.attempt_count == 2
    assert set(deleted) == {"private/exports/old.zip", expected_key}


@pytest.mark.django_db
def test_export_upload_is_deleted_when_ready_transition_fails(monkeypatch):
    org = Organization.objects.create(name="Failed Export", slug="failed-export")
    job = ExportJob.objects.create(organization=org)
    deleted = []
    monkeypatch.setattr(
        "organizations.export_tasks.build_export_archive",
        lambda _job, destination, heartbeat: destination.write(b"archive"),
    )
    monkeypatch.setattr(
        "organizations.export_tasks.default_storage.delete", deleted.append
    )
    monkeypatch.setattr(
        "organizations.export_tasks.default_storage.save", lambda name, _file: name
    )
    monkeypatch.setattr(
        "organizations.export_tasks._mark_export_ready",
        lambda _job, _key: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        export_org_data_task.run(str(job.pk))

    job.refresh_from_db()
    expected_key = f"private/exports/{org.pk}/{job.pk}.zip"
    assert job.status == ExportJob.Status.FAILED
    assert deleted.count(expected_key) == 2


@pytest.mark.django_db
def test_duplicate_delivery_does_not_run_without_job_lock(monkeypatch):
    org = Organization.objects.create(name="Locked Export", slug="locked-export")
    job = ExportJob.objects.create(organization=org)

    @contextmanager
    def lock_not_acquired(_job_id):
        yield False

    monkeypatch.setattr("organizations.export_tasks.export_job_lock", lock_not_acquired)
    with patch("organizations.export_tasks.build_export_archive") as build:
        assert export_org_data_task.run(str(job.pk)) == str(job.pk)
    build.assert_not_called()
    job.refresh_from_db()
    assert job.status == ExportJob.Status.PENDING


@pytest.mark.django_db
def test_ready_export_redelivery_is_a_noop(monkeypatch):
    org = Organization.objects.create(name="Ready Export", slug="ready-export")
    job = ExportJob.objects.create(
        organization=org,
        status=ExportJob.Status.READY,
        object_key="private/exports/ready.zip",
    )
    with patch("organizations.export_tasks.build_export_archive") as build:
        assert export_org_data_task.run(str(job.pk)) == str(job.pk)
    build.assert_not_called()
    job.refresh_from_db()
    assert job.status == ExportJob.Status.READY
    assert job.attempt_count == 0


@pytest.mark.django_db
def test_stale_export_recovery_requeues_only_inactive_jobs(settings, monkeypatch):
    settings.EXPORT_STALE_AFTER_SECONDS = 60
    org = Organization.objects.create(name="Recover Exports", slug="recover-exports")
    old = timezone.now() - timedelta(minutes=2)
    stale_pending = ExportJob.objects.create(organization=org)
    stale_processing = ExportJob.objects.create(
        organization=org,
        status=ExportJob.Status.PROCESSING,
        started_at=old,
        heartbeat_at=old,
    )
    fresh_processing = ExportJob.objects.create(
        organization=org,
        status=ExportJob.Status.PROCESSING,
        started_at=timezone.now(),
        heartbeat_at=timezone.now(),
    )
    ExportJob.objects.filter(pk=stale_pending.pk).update(queued_at=old)
    queued = []
    monkeypatch.setattr(
        "organizations.export_tasks.enqueue_export_job",
        lambda job: queued.append(job.pk),
    )

    assert recover_stale_exports.run() == 2

    stale_pending.refresh_from_db()
    stale_processing.refresh_from_db()
    fresh_processing.refresh_from_db()
    assert set(queued) == {stale_pending.pk, stale_processing.pk}
    assert stale_pending.status == ExportJob.Status.PENDING
    assert stale_processing.status == ExportJob.Status.PENDING
    assert stale_processing.started_at is None
    assert stale_processing.heartbeat_at is None
    assert fresh_processing.status == ExportJob.Status.PROCESSING


@pytest.mark.django_db
def test_retry_allows_failed_and_stale_but_rejects_active_exports(
    api_client, make_auth_headers, settings
):
    settings.EXPORT_STALE_AFTER_SECONDS = 60
    User = get_user_model()
    admin = User.objects.create_user(email="export-retry@example.com", password="pw")
    org = Organization.objects.create(name="Retry Export", slug="retry-export")
    Membership.objects.create(user=admin, organization=org, role="owner")
    old = timezone.now() - timedelta(minutes=2)
    failed = ExportJob.objects.create(
        organization=org, requested_by=admin, status=ExportJob.Status.FAILED
    )
    stale = ExportJob.objects.create(
        organization=org,
        requested_by=admin,
        status=ExportJob.Status.PROCESSING,
        started_at=old,
        heartbeat_at=old,
    )
    active = ExportJob.objects.create(
        organization=org,
        requested_by=admin,
        status=ExportJob.Status.PROCESSING,
        started_at=timezone.now(),
        heartbeat_at=timezone.now(),
    )
    headers = make_auth_headers(api_client, admin, password="pw")

    with patch("organizations.export_tasks.export_org_data_task.delay") as publish:
        failed_response = api_client.post(
            f"/orgs/{org.slug}/exports/{failed.pk}/retry/", headers=headers
        )
        stale_response = api_client.post(
            f"/orgs/{org.slug}/exports/{stale.pk}/retry/", headers=headers
        )
        active_response = api_client.post(
            f"/orgs/{org.slug}/exports/{active.pk}/retry/", headers=headers
        )

    assert failed_response.status_code == 202
    assert stale_response.status_code == 202
    assert active_response.status_code == 409
    assert publish.call_count == 2


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
