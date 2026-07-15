from datetime import timedelta
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections, transaction
from django.utils import timezone
from ninja.errors import HttpError

from core.models import IdempotencyRecord
from core.tasks import cleanup_expired_idempotency_records
from core.utils.idempotency import _operation_lock, run_idempotently
from organizations.models import Organization


def request_for(user, *, body: bytes, key: str = "request-key"):
    return SimpleNamespace(
        auth=user,
        headers={"Idempotency-Key": key},
        META={},
        method="POST",
        path="/api/v1/orgs/example/bulk-delete/",
        body=body,
        content_type="application/json",
        FILES=SimpleNamespace(getlist=lambda _field: []),
    )


@pytest.mark.django_db
def test_idempotency_persists_replays_and_rejects_payload_changes():
    user = get_user_model().objects.create_user(email="idem@example.com", password="pw")
    request = request_for(user, body=b'{"ids":[1,2]}')
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        return 204, None

    assert run_idempotently(request, operation) == (204, None)
    assert run_idempotently(request_for(user, body=b'{"ids":[1,2]}'), operation) == (
        204,
        None,
    )
    assert calls == 1
    assert IdempotencyRecord.objects.filter(user=user, status_code=204).count() == 1

    with pytest.raises(HttpError) as conflict:
        run_idempotently(
            request_for(user, body=b'{"ids":[3]}'),
            operation,
        )
    assert conflict.value.status_code == 409


@pytest.mark.django_db
def test_operation_failure_rolls_back_mutation_and_reservation():
    user = get_user_model().objects.create_user(
        email="idem-rollback@example.com", password="pw"
    )
    request = request_for(user, body=b'{"name":"temporary"}')

    def operation():
        Organization.objects.create(name="Temporary", slug="temporary")
        raise RuntimeError("operation failed")

    with pytest.raises(RuntimeError, match="operation failed"):
        run_idempotently(request, operation)

    assert not Organization.objects.filter(slug="temporary").exists()
    assert not IdempotencyRecord.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_server_error_response_rolls_back_and_is_not_persisted():
    user = get_user_model().objects.create_user(
        email="idem-server-error@example.com", password="pw"
    )
    request = request_for(user, body=b'{"name":"server-error"}')

    def operation():
        Organization.objects.create(name="Server error", slug="server-error")
        return 503, {"detail": "unavailable"}

    assert run_idempotently(request, operation) == (
        503,
        {"detail": "unavailable"},
    )
    assert not Organization.objects.filter(slug="server-error").exists()
    assert not IdempotencyRecord.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_expired_record_allows_fresh_execution():
    user = get_user_model().objects.create_user(
        email="idem-expired@example.com", password="pw"
    )
    request = request_for(user, body=b'{"ids":[1]}')
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        return 200, {"calls": calls}

    assert run_idempotently(request, operation) == (200, {"calls": 1})
    IdempotencyRecord.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    assert run_idempotently(request, operation) == (200, {"calls": 2})
    assert IdempotencyRecord.objects.count() == 1


@pytest.mark.django_db
def test_cleanup_expired_idempotency_records():
    user = get_user_model().objects.create_user(
        email="idem-cleanup@example.com", password="pw"
    )
    request = request_for(user, body=b'{"ids":[1]}')
    run_idempotently(request, lambda: (200, {"ok": True}))
    IdempotencyRecord.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    assert cleanup_expired_idempotency_records() == 1
    assert not IdempotencyRecord.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_operation_lock_returns_conflict():
    entered = Event()
    release = Event()
    errors = []
    identity_hash = "1" * 64

    def hold_lock():
        close_old_connections()
        try:
            with transaction.atomic():
                with _operation_lock(identity_hash):
                    entered.set()
                    release.wait(timeout=5)
        except Exception as exc:
            errors.append(exc)
        finally:
            close_old_connections()

    thread = Thread(target=hold_lock)
    thread.start()
    assert entered.wait(timeout=5)

    try:
        with transaction.atomic():
            with pytest.raises(HttpError) as in_progress:
                with _operation_lock(identity_hash):
                    pass
        assert in_progress.value.status_code == 409
    finally:
        release.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert errors == []
