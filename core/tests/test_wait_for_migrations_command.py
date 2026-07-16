from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.utils import OperationalError

from core.management.commands import wait_for_migrations


class FakeExecutor:
    def __init__(self, outcome):
        self.outcome = outcome
        self.loader = SimpleNamespace(
            graph=SimpleNamespace(leaf_nodes=lambda: ["leaf"])
        )

    def migration_plan(self, leaf_nodes):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def executor_factory(outcomes):
    remaining = iter(outcomes)
    calls = []

    def create(connection):
        calls.append(connection)
        return FakeExecutor(next(remaining))

    return create, calls


def test_wait_for_migrations_reloads_executor_until_current(monkeypatch):
    connection = object()
    create_executor, calls = executor_factory([["pending"], []])
    sleeps = []
    out = StringIO()

    monkeypatch.setattr(wait_for_migrations, "connections", {"default": connection})
    monkeypatch.setattr(wait_for_migrations, "MigrationExecutor", create_executor)
    monkeypatch.setattr(wait_for_migrations.time, "sleep", sleeps.append)

    call_command("wait_for_migrations", sleep=0, timeout=10, stdout=out)

    assert calls == [connection, connection]
    assert sleeps == [0]
    assert "Migrations pending" in out.getvalue()
    assert "All migrations completed!" in out.getvalue()


def test_wait_for_migrations_retries_operational_errors(monkeypatch):
    connection = object()
    create_executor, calls = executor_factory([OperationalError("not ready"), []])
    out = StringIO()

    monkeypatch.setattr(wait_for_migrations, "connections", {"default": connection})
    monkeypatch.setattr(wait_for_migrations, "MigrationExecutor", create_executor)
    monkeypatch.setattr(wait_for_migrations.time, "sleep", lambda seconds: None)

    call_command("wait_for_migrations", sleep=0, timeout=10, stdout=out)

    assert calls == [connection, connection]
    assert "Database unavailable" in out.getvalue()


def test_wait_for_migrations_raises_after_timeout(monkeypatch):
    connection = object()
    create_executor, _calls = executor_factory([["pending"]])
    out = StringIO()

    monkeypatch.setattr(wait_for_migrations, "connections", {"default": connection})
    monkeypatch.setattr(wait_for_migrations, "MigrationExecutor", create_executor)
    monkeypatch.setattr(
        wait_for_migrations,
        "time",
        SimpleNamespace(
            monotonic=iter([0.0, 2.0]).__next__,
            sleep=lambda seconds: None,
        ),
    )

    with pytest.raises(CommandError, match="Timed out waiting for migrations"):
        call_command("wait_for_migrations", sleep=0, timeout=1, stdout=out)
