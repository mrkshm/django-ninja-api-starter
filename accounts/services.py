import logging
from typing import cast

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone
from ninja.errors import HttpError
from ninja_jwt.exceptions import TokenError
from ninja_jwt.settings import api_settings
from ninja_jwt.tokens import RefreshToken, UntypedToken

from accounts.models import AuthSession
from accounts.validation import normalize_and_validate_email
from core.email_utils import render_email_template
from core.tasks import send_email_task

User = get_user_model()
logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    return normalize_and_validate_email(email)


def validate_new_password(password: str, user=None) -> None:
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        raise HttpError(400, " ".join(exc.messages)) from exc


def authenticate_for_token(email: str, password: str):
    user = authenticate(email=normalize_email(email), password=password)
    if user is None or not user.is_active:
        raise HttpError(401, "Invalid credentials")

    require_verification = getattr(
        settings, "REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN", True
    )
    return user, not (require_verification and not user.email_verified)


def _populate_refresh_claims(refresh: RefreshToken, user, session: AuthSession) -> None:
    refresh["auth_version"] = user.auth_version
    refresh["session_id"] = str(session.id)


def create_auth_session(user, *, device_name: str = "") -> AuthSession:
    return AuthSession.objects.create(
        user=user,
        auth_version=user.auth_version,
        device_name=device_name.strip(),
        expires_at=timezone.now() + api_settings.REFRESH_TOKEN_LIFETIME,
    )


def issue_token_pair(user, *, device_name: str = "", session=None) -> tuple[str, str]:
    session = session or create_auth_session(user, device_name=device_name)
    refresh = cast(RefreshToken, RefreshToken.for_user(user))
    _populate_refresh_claims(refresh, user, session)
    return str(refresh.access_token), str(refresh)


def rotate_token_pair(raw_refresh: str) -> tuple[str, str]:
    try:
        refresh = RefreshToken(raw_refresh)
        session_id = refresh.get("session_id")
        user_id = refresh.get(api_settings.USER_ID_CLAIM)
        auth_version = refresh.get("auth_version")
        if not session_id or user_id is None or auth_version is None:
            raise TokenError("Refresh token has no session")

    except (TokenError, ValueError) as exc:
        # A correctly signed token that is no longer accepted (most commonly a
        # replayed, blacklisted refresh token) revokes its whole device session.
        try:
            decoded = UntypedToken(raw_refresh)
            replayed_session_id = decoded.get("session_id")
            if replayed_session_id:
                AuthSession.objects.filter(
                    id=replayed_session_id,
                    revoked_at__isnull=True,
                ).update(revoked_at=timezone.now())
        except TokenError, ValueError:
            pass
        raise HttpError(401, "Invalid or expired refresh token") from exc

    rejected = False
    token_pair: tuple[str, str] | None = None
    with transaction.atomic():
        try:
            user = User.objects.select_for_update().get(pk=user_id)
        except User.DoesNotExist as exc:
            raise HttpError(401, "Invalid or expired refresh token") from exc
        try:
            session = AuthSession.objects.select_for_update().get(
                id=session_id,
                user_id=user.pk,
            )
        except AuthSession.DoesNotExist as exc:
            raise HttpError(401, "Invalid or expired refresh token") from exc

        if (
            not user.is_active
            or user.auth_version != auth_version
            or session.auth_version != user.auth_version
            or not session.is_active
        ):
            session.revoke()
            rejected = True
        else:
            try:
                refresh.blacklist()
            except AttributeError:
                logger.error("JWT blacklist app is not configured")
                raise HttpError(500, "Token revocation is unavailable")

            session.last_used_at = timezone.now()
            session.expires_at = timezone.now() + api_settings.REFRESH_TOKEN_LIFETIME
            session.save(update_fields=["last_used_at", "expires_at"])
            token_pair = issue_token_pair(user, session=session)

    if rejected or token_pair is None:
        raise HttpError(401, "Invalid or expired refresh token")
    return token_pair


def revoke_session_from_refresh(raw_refresh: str) -> None:
    try:
        refresh = RefreshToken(raw_refresh)
        session_id = refresh.get("session_id")
        if not session_id:
            raise TokenError("Refresh token has no session")
        AuthSession.objects.filter(id=session_id, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        refresh.blacklist()
    except (TokenError, ValueError) as exc:
        raise HttpError(401, "Invalid or expired refresh token") from exc


def revoke_all_sessions(user) -> None:
    now = timezone.now()
    AuthSession.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=now
    )
    User.objects.filter(pk=user.pk).update(auth_version=F("auth_version") + 1)
    user.refresh_from_db(fields=["auth_version"])


@transaction.atomic
def set_user_active_status(user, *, is_active: bool) -> None:
    if not is_active:
        from organizations.services import assert_user_can_be_deactivated

        assert_user_can_be_deactivated(user)
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    User.objects.filter(pk=locked_user.pk).update(is_active=is_active)
    locked_user.is_active = is_active
    revoke_all_sessions(locked_user)
    user.is_active = is_active
    user.auth_version = locked_user.auth_version


def deactivate_user(user) -> None:
    set_user_active_status(user, is_active=False)


def delete_user_account(user) -> None:
    from organizations.models import Organization
    from organizations.services import ActiveOwnerRequiredError

    try:
        with transaction.atomic():
            organization_ids = list(
                Organization.objects.filter(
                    Q(type="personal", creator_id=user.pk)
                    | Q(
                        type="group",
                        memberships__user_id=user.pk,
                        memberships__role="owner",
                    )
                )
                .values_list("pk", flat=True)
                .distinct()
            )
            organizations = list(
                Organization.objects.select_for_update()
                .filter(pk__in=organization_ids)
                .order_by("pk")
            )
            locked_user = User.objects.select_for_update().get(pk=user.pk)

            for organization in organizations:
                if organization.type != "group":
                    continue
                still_owner = organization.memberships.filter(
                    user_id=locked_user.pk,
                    role="owner",
                ).exists()
                if not still_owner:
                    continue
                has_successor = (
                    organization.memberships.filter(
                        role="owner",
                        user__is_active=True,
                    )
                    .exclude(user_id=locked_user.pk)
                    .exists()
                )
                if not has_successor:
                    raise ActiveOwnerRequiredError(
                        f"Promote another active owner for {organization.name} first."
                    )

            personal_ids = [
                organization.pk
                for organization in organizations
                if organization.type == "personal"
                and organization.creator_id == locked_user.pk
            ]
            Organization.objects.filter(pk__in=personal_ids).delete()
            locked_user.delete()
    except IntegrityError as exc:
        raise ActiveOwnerRequiredError(
            "Account deletion would leave an organization without an active owner."
        ) from exc


def send_templated_email(
    template_name: str, context: dict, recipients: list[str]
) -> None:
    subject, body_text = render_email_template(template_name, context)
    try:
        send_email_task.delay(subject, body_text, recipients)
    except Exception:
        logger.exception(
            "accounts:email_task_publish_failed template=%s",
            template_name,
        )
        raise
