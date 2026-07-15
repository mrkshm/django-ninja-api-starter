from types import SimpleNamespace

from core.utils.logging import request_id_context
from DjangoApiStarter.celery import (
    add_request_id_header,
    bind_task_request_id,
    clear_task_request_id,
)


def test_request_id_propagates_through_celery_headers():
    token = request_id_context.set("request-123")
    try:
        headers = {}
        add_request_id_header(headers=headers)
        assert headers["request_id"] == "request-123"

        request_id_context.set(None)
        task = SimpleNamespace(
            request=SimpleNamespace(request_id=headers["request_id"])
        )
        bind_task_request_id(task=task)
        assert request_id_context.get() == "request-123"

        clear_task_request_id()
        assert request_id_context.get() is None
    finally:
        request_id_context.reset(token)
