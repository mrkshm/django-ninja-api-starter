from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import PendingEmailChange, PendingPasswordReset
from accounts.services import revoke_all_sessions, validate_new_password
from accounts.tokens import generate_raw_token, hash_token

User = get_user_model()
audit_logger = logging.getLogger("audit")


class AccountOperationError(ValueError):
    pass


@dataclass(frozen=True)
class PasswordResetDelivery:
    user_id: int
    email: str
    display_name: str
    raw_token: str


@dataclass(frozen=True)
class EmailChangeResult:
    user_id: int
    old_email: str
    new_email: str


@dataclass(frozen=True)
class EmailChangeDelivery:
    pending_id: int
    user_id: int
    old_email: str
    new_email: str
    display_name: str
    raw_token: str
    token_hash: str


@transaction.atomic
def change_password(*, user_id: int, old_password: str, new_password: str) -> None:
    user = User.objects.select_for_update().get(pk=user_id)
    if not user.check_password(old_password):
        raise AccountOperationError("Old password is incorrect")
    validate_new_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    revoke_all_sessions(user)
    transaction.on_commit(
        lambda: audit_logger.info("audit:password_changed user=%s", user_id)
    )


def rotate_password_reset(
    *, email: str, expiry_hours: int
) -> PasswordResetDelivery | None:
    user_id = (
        User.objects.filter(email__iexact=email).values_list("pk", flat=True).first()
    )
    if user_id is None:
        return None

    raw_token = generate_raw_token()
    token_hash = hash_token(raw_token)
    expires_at = timezone.now() + timedelta(hours=expiry_hours)
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user_id)
        PendingPasswordReset.objects.update_or_create(
            user=user,
            defaults={"token": token_hash, "expires_at": expires_at},
        )
    display_name = f"{user.first_name} {user.last_name}".strip() or user.email
    return PasswordResetDelivery(
        user_id=user.pk,
        email=user.email,
        display_name=display_name,
        raw_token=raw_token,
    )


def request_email_change(
    *,
    user_id: int,
    new_email: str,
    current_password: str,
    expiry_hours: int,
) -> EmailChangeDelivery:
    raw_token = generate_raw_token()
    token_hash = hash_token(raw_token)
    expires_at = timezone.now() + timedelta(hours=expiry_hours)
    try:
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user_id)
            if new_email == user.email.strip().lower():
                raise AccountOperationError(
                    "New email must differ from the current email."
                )
            if not user.check_password(current_password):
                raise AccountOperationError("Password is incorrect")
            if (
                User.objects.filter(email__iexact=new_email)
                .exclude(pk=user.pk)
                .exists()
            ):
                raise AccountOperationError("Email already taken")
            pending, _ = PendingEmailChange.objects.update_or_create(
                user=user,
                defaults={
                    "new_email": new_email,
                    "token": token_hash,
                    "expires_at": expires_at,
                    "auth_version": user.auth_version,
                },
            )
    except IntegrityError as exc:
        raise AccountOperationError("Email already taken") from exc

    display_name = f"{user.first_name} {user.last_name}".strip() or user.email
    return EmailChangeDelivery(
        pending_id=pending.pk,
        user_id=user.pk,
        old_email=user.email,
        new_email=new_email,
        display_name=display_name,
        raw_token=raw_token,
        token_hash=token_hash,
    )


def confirm_password_reset(*, raw_token: str, new_password: str) -> None:
    token_hash = hash_token(raw_token)
    user_id = (
        PendingPasswordReset.objects.filter(token=token_hash)
        .values_list("user_id", flat=True)
        .first()
    )
    if user_id is None:
        raise AccountOperationError("Invalid or expired token.")

    error: str | None = None
    with transaction.atomic():
        try:
            user = User.objects.select_for_update().get(pk=user_id)
        except User.DoesNotExist:
            user = None
            error = "Invalid or expired token."
        if user is None:
            pending = None
        else:
            try:
                pending = PendingPasswordReset.objects.select_for_update().get(
                    token=token_hash,
                    user_id=user.pk,
                )
            except PendingPasswordReset.DoesNotExist:
                pending = None
                error = "Invalid or expired token."
        if pending is not None and user is not None:
            if pending.is_expired():
                pending.delete()
                error = "Token has expired."
            else:
                validate_new_password(new_password, user=user)
                user.set_password(new_password)
                user.save(update_fields=["password", "updated_at"])
                revoke_all_sessions(user)
                pending.delete()
                transaction.on_commit(
                    lambda: audit_logger.info(
                        "audit:password_reset_completed user=%s", user_id
                    )
                )

    if error is not None:
        raise AccountOperationError(error)


def confirm_email_change(*, raw_token: str) -> EmailChangeResult:
    token_hash = hash_token(raw_token)
    user_id = (
        PendingEmailChange.objects.filter(token=token_hash)
        .values_list("user_id", flat=True)
        .first()
    )
    if user_id is None:
        raise AccountOperationError("Invalid or expired token.")

    error: str | None = None
    result: EmailChangeResult | None = None
    try:
        with transaction.atomic():
            try:
                locked_user = User.objects.select_for_update().get(pk=user_id)
            except User.DoesNotExist:
                user = None
                pending = None
                error = "Invalid or expired token."
            else:
                user = locked_user
                try:
                    pending = PendingEmailChange.objects.select_for_update().get(
                        token=token_hash, user_id=locked_user.pk
                    )
                except PendingEmailChange.DoesNotExist:
                    pending = None
                    error = "Invalid or expired token."
            if pending is not None and user is not None:
                if pending.is_expired():
                    pending.delete()
                    error = "Token has expired."
                elif pending.auth_version != user.auth_version:
                    pending.delete()
                    error = "Invalid or expired token."
                elif (
                    User.objects.filter(email__iexact=pending.new_email)
                    .exclude(pk=user.pk)
                    .exists()
                ):
                    pending.delete()
                    error = "Email already taken."
                else:
                    result = EmailChangeResult(
                        user_id=user.pk,
                        old_email=user.email,
                        new_email=pending.new_email,
                    )
                    user.email = pending.new_email
                    user.save(update_fields=["email", "updated_at"])
                    revoke_all_sessions(user)
                    pending.delete()
                    transaction.on_commit(
                        lambda: audit_logger.info(
                            "audit:email_change_completed user=%s", user_id
                        )
                    )
    except IntegrityError as exc:
        raise AccountOperationError("Email already taken.") from exc

    if error is not None or result is None:
        raise AccountOperationError(error or "Invalid or expired token.")
    return result
