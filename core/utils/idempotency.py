from __future__ import annotations

import hashlib
import json
from typing import Any

from django.core.cache import cache
from ninja.errors import HttpError

from core.utils.auth_utils import get_request_user

IDEMPOTENCY_TTL = 24 * 60 * 60
IDEMPOTENCY_IN_PROGRESS_TTL = 5 * 60
HEADER_NAME = "Idempotency-Key"


def _client_key(request) -> str | None:
    value = request.headers.get(HEADER_NAME) or request.META.get("HTTP_IDEMPOTENCY_KEY")
    if not value:
        return None
    value = str(value).strip()
    if not value or len(value) > 128:
        raise HttpError(400, "Invalid Idempotency-Key.")
    return value


def _cache_key(user_id: Any, method: str, path: str, client_key: str) -> str:
    identity = f"{user_id}:{method.upper()}:{path}:{client_key}"
    return f"idem:{hashlib.sha256(identity.encode()).hexdigest()}"


def _request_fingerprint(request) -> str:
    try:
        body = getattr(request, "body", b"") or b""
    except Exception:
        body = b""
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


def _request_cache_identity(request) -> tuple[str, str] | None:
    client_key = _client_key(request)
    if client_key is None:
        return None
    user_id = getattr(get_request_user(request), "id", "anon")
    key = _cache_key(user_id, request.method, request.path, client_key)
    return key, _request_fingerprint(request)


def read_cached_response(request) -> tuple[int, Any] | None:
    """Return a completed response or atomically reserve this operation."""
    identity = _request_cache_identity(request)
    if identity is None:
        return None
    key, fingerprint = identity
    reservation = {"state": "in_progress", "fingerprint": fingerprint}
    if cache.add(key, reservation, timeout=IDEMPOTENCY_IN_PROGRESS_TTL):
        return None

    payload = cache.get(key) or {}
    if payload.get("fingerprint") != fingerprint:
        raise HttpError(
            409, "Idempotency-Key was already used for a different request."
        )
    if payload.get("state") == "in_progress":
        raise HttpError(
            409, "An operation with this Idempotency-Key is already in progress."
        )
    return int(payload.get("status", 200)), payload.get("data")


def store_cached_response(request, status: int, data: Any) -> None:
    identity = _request_cache_identity(request)
    if identity is None:
        return
    # Cache all completed non-server-error responses. Some bulk operations
    # intentionally return 4xx after applying a documented partial result.
    if not 200 <= status < 500:
        return
    key, fingerprint = identity
    cache.set(
        key,
        {
            "state": "complete",
            "fingerprint": fingerprint,
            "status": status,
            "data": data,
        },
        timeout=IDEMPOTENCY_TTL,
    )
