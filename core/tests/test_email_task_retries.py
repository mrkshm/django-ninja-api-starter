from unittest.mock import patch

import pytest

from core.tasks import send_email_task


def test_email_task_does_not_retry_programmer_errors():
    with patch("core.tasks._send_email_task", side_effect=ValueError("bug")):
        with pytest.raises(ValueError, match="bug"):
            send_email_task.run("Subject", "Body", ["to@example.com"])


def test_email_task_retries_transient_connection_errors():
    retryable = send_email_task.autoretry_for

    assert any(issubclass(ConnectionError, error_type) for error_type in retryable)
    assert not any(issubclass(ValueError, error_type) for error_type in retryable)
