import json
import logging
import sys

from django.test import RequestFactory

from core.api_errors import unhandled_error_response
from core.utils.logging import JSONFormatter


def test_json_formatter_serializes_exception_traceback():
    try:
        raise RuntimeError("formatter boom")
    except RuntimeError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=10,
        msg="Unhandled exception",
        args=(),
        exc_info=exc_info,
    )

    payload = json.loads(JSONFormatter().format(record))

    assert payload["msg"] == "Unhandled exception"
    assert "Traceback (most recent call last)" in payload["exception"]
    assert "RuntimeError: formatter boom" in payload["exception"]


def test_json_formatter_serializes_stack_info():
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=20,
        msg="Diagnostic stack",
        args=(),
        exc_info=None,
    )
    record.stack_info = "Stack (most recent call last):\n  test frame"

    payload = json.loads(JSONFormatter().format(record))

    assert payload["stack"] == record.stack_info
    assert "exception" not in payload


def test_unhandled_error_logs_explicit_exception_tuple(caplog):
    request = RequestFactory().get("/broken")
    exception = RuntimeError("outside an except block")

    with caplog.at_level(logging.ERROR, logger="core.api_errors"):
        response = unhandled_error_response(request, exception)

    record = caplog.records[-1]
    assert response.status_code == 500
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
    assert record.exc_info[1] is exception
