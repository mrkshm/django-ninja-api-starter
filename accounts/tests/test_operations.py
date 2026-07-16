from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import AuthSession, PendingPasswordReset
from accounts.operations import AccountOperationError, change_password
from accounts.tokens import hash_token

User = get_user_model()


@pytest.mark.django_db
def test_password_change_rolls_back_if_session_revocation_fails():
    user = User.objects.create_user(email="atomic@example.com", password="oldpass123")
    with (
        patch(
            "accounts.operations.revoke_all_sessions",
            side_effect=RuntimeError("session mutation failed"),
        ),
        pytest.raises(RuntimeError, match="session mutation failed"),
    ):
        change_password(
            user_id=user.pk,
            old_password="oldpass123",
            new_password="newpass456",
        )

    user.refresh_from_db()
    assert user.check_password("oldpass123")
    assert not user.check_password("newpass456")


@pytest.mark.django_db
def test_incorrect_password_changes_no_credential_or_session_state():
    user = User.objects.create_user(email="wrong@example.com", password="oldpass123")
    session = AuthSession.objects.create(
        user=user,
        auth_version=user.auth_version,
        expires_at=timezone.now() + timezone.timedelta(days=1),
    )

    with pytest.raises(AccountOperationError, match="incorrect"):
        change_password(
            user_id=user.pk,
            old_password="wrong",
            new_password="newpass456",
        )

    user.refresh_from_db()
    session.refresh_from_db()
    assert user.check_password("oldpass123")
    assert session.revoked_at is None


@pytest.mark.django_db
def test_weak_password_is_reported_as_an_operation_error():
    user = User.objects.create_user(
        email="weak-operation@example.com", password="oldpass123"
    )

    with pytest.raises(AccountOperationError):
        change_password(
            user_id=user.pk,
            old_password="oldpass123",
            new_password="password",
        )

    user.refresh_from_db()
    assert user.check_password("oldpass123")


@pytest.mark.django_db
def test_pending_reset_requires_explicit_token_hash():
    user = User.objects.create_user(email="token-required@example.com", password="pw")
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            PendingPasswordReset.objects.create(
                user=user,
                expires_at=timezone.now() + timezone.timedelta(hours=1),
            )


@pytest.mark.django_db
def test_pending_reset_stores_supplied_hash_unchanged():
    user = User.objects.create_user(email="token-hash@example.com", password="pw")
    token_hash = hash_token("raw-token")
    pending = PendingPasswordReset.objects.create(
        user=user,
        token=token_hash,
        expires_at=timezone.now() + timezone.timedelta(hours=1),
    )
    assert pending.token == token_hash
