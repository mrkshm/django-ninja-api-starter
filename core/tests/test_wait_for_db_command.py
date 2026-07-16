from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.utils import OperationalError

from core.management.commands import wait_for_db


class FakeConnection:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.attempts = 0

    def ensure_connection(self):
        self.attempts += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome


def test_wait_for_db_retries_until_database_is_available(monkeypatch):
    connection = FakeConnection([OperationalError("not ready"), None])
    sleeps = []
    out = StringIO()

    monkeypatch.setattr(wait_for_db, "connections", {"default": connection})
    monkeypatch.setattr(wait_for_db.time, "sleep", sleeps.append)

    call_command("wait_for_db", sleep=0, stdout=out)

    assert connection.attempts == 2
    assert sleeps == [0]
    assert "Database unavailable" in out.getvalue()
    assert "Database available!" in out.getvalue()


def test_wait_for_db_raises_after_timeout(monkeypatch):
    connection = FakeConnection([OperationalError("not ready")])
    out = StringIO()

    monkeypatch.setattr(wait_for_db, "connections", {"default": connection})
    monkeypatch.setattr(
        wait_for_db,
        "time",
        SimpleNamespace(
            monotonic=iter([0, 2]).__next__,
            sleep=lambda seconds: None,
        ),
    )

    with pytest.raises(CommandError, match="Database unavailable"):
        call_command("wait_for_db", sleep=0, timeout=1, stdout=out)

    assert connection.attempts == 1
