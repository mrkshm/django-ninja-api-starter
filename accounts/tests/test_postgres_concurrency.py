from __future__ import annotations

import threading
from collections.abc import Callable

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone
from ninja.errors import HttpError

from accounts.models import PendingEmailChange, PendingPasswordReset, User
from accounts.operations import (
    AccountOperationError,
    change_password,
    confirm_email_change,
    confirm_password_reset,
)
from accounts.services import (
    issue_token_pair,
    rotate_token_pair,
    set_user_active_status,
)
from accounts.tokens import hash_token
from organizations.models import Membership
from organizations.services import ActiveOwnerRequiredError, create_group_organization

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="row-lock behavior requires PostgreSQL",
    ),
]


def run_concurrently(*operations: Callable[[], None]):
    barrier = threading.Barrier(len(operations))
    outcomes: list[BaseException | None] = []
    outcomes_lock = threading.Lock()

    def run(operation: Callable[[], None]) -> None:
        close_old_connections()
        outcome: BaseException | None = None
        try:
            barrier.wait(timeout=5)
            operation()
        except BaseException as exc:
            outcome = exc
        finally:
            close_old_connections()
            with outcomes_lock:
                outcomes.append(outcome)

    threads = [
        threading.Thread(target=run, args=(operation,)) for operation in operations
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(
        not thread.is_alive() for thread in threads
    ), "possible database deadlock"
    return outcomes


def test_password_reset_token_succeeds_only_once_under_concurrency():
    user = User.objects.create_user(email="reset-race@example.com", password="oldpass")
    token = "reset-race-token"
    PendingPasswordReset.objects.create(
        user=user,
        token=hash_token(token),
        expires_at=timezone.now() + timezone.timedelta(hours=1),
    )

    outcomes = run_concurrently(
        lambda: confirm_password_reset(raw_token=token, new_password="first-pass-123"),
        lambda: confirm_password_reset(raw_token=token, new_password="second-pass-123"),
    )

    assert sum(outcome is None for outcome in outcomes) == 1
    assert sum(isinstance(outcome, AccountOperationError) for outcome in outcomes) == 1
    assert not PendingPasswordReset.objects.filter(user=user).exists()


def test_email_confirmation_and_password_change_do_not_deadlock():
    user = User.objects.create_user(email="email-race@example.com", password="oldpass")
    token = "email-race-token"
    PendingEmailChange.objects.create(
        user=user,
        new_email="email-race-new@example.com",
        auth_version=user.auth_version,
        token=hash_token(token),
        expires_at=timezone.now() + timezone.timedelta(hours=1),
    )

    outcomes = run_concurrently(
        lambda: confirm_email_change(raw_token=token),
        lambda: change_password(
            user_id=user.pk,
            old_password="oldpass",
            new_password="newpass-123",
        ),
    )

    assert any(outcome is None for outcome in outcomes)
    assert all(
        outcome is None or isinstance(outcome, AccountOperationError)
        for outcome in outcomes
    )
    user.refresh_from_db()
    assert user.check_password("newpass-123")


def test_refresh_rotation_and_password_change_do_not_deadlock():
    user = User.objects.create_user(
        email="refresh-race@example.com", password="oldpass"
    )
    _access, refresh = issue_token_pair(user)

    outcomes = run_concurrently(
        lambda: rotate_token_pair(refresh),
        lambda: change_password(
            user_id=user.pk,
            old_password="oldpass",
            new_password="newpass-123",
        ),
    )

    assert any(outcome is None for outcome in outcomes)
    assert all(
        outcome is None or isinstance(outcome, HttpError) for outcome in outcomes
    )


def test_shared_organization_serializes_concurrent_deactivation():
    first = User.objects.create_user(email="owner-one@example.com", password="pw")
    second = User.objects.create_user(email="owner-two@example.com", password="pw")
    organization = create_group_organization(
        name="Shared owners",
        slug="shared-owners",
        owner=first,
    )
    Membership.objects.create(user=second, organization=organization, role="owner")

    outcomes = run_concurrently(
        lambda: set_user_active_status(first, is_active=False),
        lambda: set_user_active_status(second, is_active=False),
    )

    assert sum(outcome is None for outcome in outcomes) == 1
    assert (
        sum(isinstance(outcome, ActiveOwnerRequiredError) for outcome in outcomes) == 1
    )
    assert (
        User.objects.filter(pk__in=(first.pk, second.pk), is_active=True).count() == 1
    )
