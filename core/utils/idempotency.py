from __future__ import annotations
import json
from typing import Any, Optional, Tuple
from django.core.cache import cache

# TTL in seconds (24h)
IDEMPOTENCY_TTL = 24 * 60 * 60

HEADER_NAME = "Idempotency-Key"


def _cache_key(user_id: Any, method: str, path: str, client_key: str) -> str:
    return f"idem:{user_id}:{method}:{path}:{client_key}"


def read_cached_response(request) -> Optional[Tuple[int, Any]]:
    """Return (status, data) if an idempotent response exists for this request.
    Requires the client to send an Idempotency-Key header.
    """
    client_key = request.headers.get(HEADER_NAME) or request.META.get("HTTP_IDEMPOTENCY_KEY")
    if not client_key:
        return None
    user_id = getattr(request.user, "id", "anon")
    key = _cache_key(user_id, request.method, request.path, client_key)
    payload = cache.get(key)
    if not payload:
        return None
    try:
        status = payload.get("status", 200)
        data = payload.get("data")
        return status, data
    except Exception:
        return None


def store_cached_response(request, status: int, data: Any) -> None:
    client_key = request.headers.get(HEADER_NAME) or request.META.get("HTTP_IDEMPOTENCY_KEY")
    if not client_key:
        return
    user_id = getattr(request.user, "id", "anon")
    key = _cache_key(user_id, request.method, request.path, client_key)
    cache.set(key, {"status": status, "data": data}, timeout=IDEMPOTENCY_TTL)
