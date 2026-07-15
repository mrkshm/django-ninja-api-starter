from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import connection, transaction
from django.http import HttpRequest
from django.utils import timezone
from ninja.errors import HttpError

from accounts.models import User
from core.models import IdempotencyRecord
from core.utils.auth_utils import get_request_user

IDEMPOTENCY_TTL = 24 * 60 * 60
HEADER_NAME = "Idempotency-Key"
_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class RequestIdentity:
    identity_hash: str
    fingerprint: str
    user: User
    method: str
    path: str


def _client_key(request: HttpRequest) -> str | None:
    value = request.headers.get(HEADER_NAME) or request.META.get("HTTP_IDEMPOTENCY_KEY")
    if not value:
        return None
    value = str(value).strip()
    if not value or len(value) > 128:
        raise HttpError(400, "Invalid Idempotency-Key.")
    return value


def _identity_hash(user_id: int, method: str, path: str, client_key: str) -> str:
    identity = f"{user_id}:{method.upper()}:{path}:{client_key}"
    return hashlib.sha256(identity.encode()).hexdigest()


def _request_fingerprint(request: HttpRequest) -> str:
    try:
        body = getattr(request, "body", b"") or b""
    except Exception as exc:
        raise HttpError(
            400,
            "Request body cannot be fingerprinted after multipart parsing; "
            "provide an explicit fingerprint.",
        ) from exc
    if isinstance(body, str):
        body = body.encode()
    content_type = str(getattr(request, "content_type", "") or "")
    normalized_body: bytes
    if "json" in content_type or body[:1] in {b"{", b"["}:
        try:
            normalized_body = json.dumps(
                json.loads(body), sort_keys=True, separators=(",", ":")
            ).encode()
        except TypeError, ValueError, UnicodeDecodeError:
            normalized_body = body
    else:
        normalized_body = body

    file_metadata: list[tuple[str, int, str]] = []
    files = getattr(request, "FILES", None)
    if files is not None and hasattr(files, "getlist"):
        for field in ("file", "files"):
            for uploaded in files.getlist(field):
                file_metadata.append(
                    (
                        str(getattr(uploaded, "name", "")),
                        int(getattr(uploaded, "size", 0) or 0),
                        str(getattr(uploaded, "content_type", "") or ""),
                    )
                )
    digest = hashlib.sha256()
    digest.update(normalized_body)
    digest.update(json.dumps(sorted(file_metadata), separators=(",", ":")).encode())
    return digest.hexdigest()


def _request_identity(
    request: HttpRequest, *, request_fingerprint: str | None = None
) -> RequestIdentity | None:
    client_key = _client_key(request)
    if client_key is None:
        return None
    user = get_request_user(request)
    method = str(request.method).upper()
    path = str(request.path)
    return RequestIdentity(
        identity_hash=_identity_hash(user.id, method, path, client_key),
        fingerprint=(
            request_fingerprint
            if request_fingerprint is not None
            else _request_fingerprint(request)
        ),
        user=user,
        method=method,
        path=path,
    )


def _postgres_lock_key(identity_hash: str) -> int:
    return int.from_bytes(bytes.fromhex(identity_hash[:16]), "big", signed=True)


@contextmanager
def _operation_lock(identity_hash: str) -> Iterator[None]:
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_xact_lock(%s)",
                [_postgres_lock_key(identity_hash)],
            )
            acquired = bool(cursor.fetchone()[0])
        if not acquired:
            raise HttpError(
                409, "An operation with this Idempotency-Key is already in progress."
            )
        yield
        return

    # SQLite is used only for local development and fast unit tests. This
    # mirrors PostgreSQL's non-blocking lock within the current process.
    with _LOCAL_LOCKS_GUARD:
        local_lock = _LOCAL_LOCKS.setdefault(identity_hash, threading.Lock())
        acquired = local_lock.acquire(blocking=False)
    if not acquired:
        raise HttpError(
            409, "An operation with this Idempotency-Key is already in progress."
        )
    try:
        yield
    finally:
        with _LOCAL_LOCKS_GUARD:
            local_lock.release()
            _LOCAL_LOCKS.pop(identity_hash, None)


def run_idempotently(
    request: HttpRequest,
    operation: Callable[[], tuple[int, Any]],
    *,
    request_fingerprint: str | None = None,
) -> tuple[int, Any]:
    """Execute and persist a database mutation and its response atomically."""
    identity = _request_identity(request, request_fingerprint=request_fingerprint)
    if identity is None:
        with transaction.atomic():
            return operation()

    with transaction.atomic():
        with _operation_lock(identity.identity_hash):
            record = IdempotencyRecord.objects.filter(
                identity_hash=identity.identity_hash
            ).first()
            if record and record.expires_at <= timezone.now():
                record.delete()
                record = None

            if record:
                if record.request_fingerprint != identity.fingerprint:
                    raise HttpError(
                        409,
                        "Idempotency-Key was already used for a different request.",
                    )
                return record.status_code, record.response_data

            status, data = operation()
            if 200 <= status < 500:
                now = timezone.now()
                IdempotencyRecord.objects.create(
                    identity_hash=identity.identity_hash,
                    request_fingerprint=identity.fingerprint,
                    user=identity.user,
                    method=identity.method,
                    path=identity.path,
                    status_code=status,
                    response_data=data,
                    completed_at=now,
                    expires_at=now + timedelta(seconds=IDEMPOTENCY_TTL),
                )
            else:
                transaction.set_rollback(True)
            return status, data
