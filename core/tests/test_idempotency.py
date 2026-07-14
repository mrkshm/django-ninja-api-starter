from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from ninja.errors import HttpError

from core.utils.idempotency import read_cached_response, store_cached_response


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
def test_idempotency_reserves_replays_and_rejects_payload_changes():
    cache.clear()
    user = get_user_model().objects.create_user(email="idem@example.com", password="pw")
    first = request_for(user, body=b'{"ids":[1,2]}')

    assert read_cached_response(first) is None
    with pytest.raises(HttpError) as in_progress:
        read_cached_response(request_for(user, body=b'{"ids":[1,2]}'))
    assert in_progress.value.status_code == 409

    store_cached_response(first, 204, None)
    assert read_cached_response(request_for(user, body=b'{"ids":[1,2]}')) == (204, None)

    with pytest.raises(HttpError) as conflict:
        read_cached_response(request_for(user, body=b'{"ids":[3]}'))
    assert conflict.value.status_code == 409
