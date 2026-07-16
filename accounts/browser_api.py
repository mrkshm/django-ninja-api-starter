import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from ninja import Router, Status
from ninja.errors import HttpError
from ninja.utils import check_csrf

from accounts.operations import (
    AccountOperationConflict,
    AccountOperationError,
    confirm_registration,
)
from accounts.schemas import (
    BrowserAccessTokenOutputSchema,
    BrowserRegistrationOutputSchema,
    BrowserTokenOutputSchema,
    CsrfTokenOutputSchema,
    RegistrationVerificationSchema,
    TokenPairInputSchema,
    UnverifiedUserSchema,
)
from accounts.services import (
    authenticate_for_token,
    issue_token_pair,
    revoke_session_from_refresh,
    rotate_token_pair,
)
from accounts.throttles import login_throttle, logout_throttle, refresh_throttle
from core.schemas import DetailResponse

browser_auth_router = Router()
audit_logger = logging.getLogger("audit")


def _require_csrf(request: HttpRequest) -> None:
    """Apply Django's origin and token checks to Ninja's exempt route wrapper."""
    if check_csrf(request) is not None:
        raise HttpError(403, "CSRF verification failed")


def _set_refresh_cookie(response: HttpResponse, refresh: str) -> None:
    response.set_cookie(
        key=settings.BROWSER_REFRESH_COOKIE_NAME,
        value=refresh,
        max_age=settings.BROWSER_REFRESH_COOKIE_MAX_AGE,
        path=settings.BROWSER_REFRESH_COOKIE_PATH,
        secure=settings.BROWSER_REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )


def _prevent_auth_response_storage(response: HttpResponse) -> None:
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"


def _clear_refresh_cookie(response: HttpResponse) -> None:
    response.set_cookie(
        key=settings.BROWSER_REFRESH_COOKIE_NAME,
        value="",
        max_age=0,
        path=settings.BROWSER_REFRESH_COOKIE_PATH,
        secure=settings.BROWSER_REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )


@browser_auth_router.get("/csrf", response=CsrfTokenOutputSchema)
def browser_csrf(request: HttpRequest, response: HttpResponse) -> CsrfTokenOutputSchema:
    _prevent_auth_response_storage(response)
    return CsrfTokenOutputSchema(csrf_token=get_token(request))


@browser_auth_router.post(
    "/login",
    response={200: BrowserTokenOutputSchema, 403: UnverifiedUserSchema},
    throttle=[login_throttle],
)
def browser_login(
    request: HttpRequest,
    response: HttpResponse,
    data: TokenPairInputSchema,
) -> BrowserTokenOutputSchema | Status[UnverifiedUserSchema]:
    _require_csrf(request)
    _prevent_auth_response_storage(response)
    try:
        user, is_verified = authenticate_for_token(data.email, data.password)
    except HttpError:
        audit_logger.warning(
            "audit:browser_login_failed ip=%s",
            request.META.get("REMOTE_ADDR"),
        )
        raise
    if not is_verified:
        return Status(
            403,
            UnverifiedUserSchema(
                detail="Please verify your email address before logging in.",
                email_verified=False,
            ),
        )

    access, refresh = issue_token_pair(user, device_name=data.device_name or "")
    _set_refresh_cookie(response, refresh)
    audit_logger.info("audit:browser_login_succeeded user=%s", user.pk)
    return BrowserTokenOutputSchema(access=access, email=user.email)


@browser_auth_router.post(
    "/verify-registration",
    response=BrowserRegistrationOutputSchema,
)
def browser_verify_registration(
    request: HttpRequest,
    response: HttpResponse,
    data: RegistrationVerificationSchema,
) -> BrowserRegistrationOutputSchema:
    _require_csrf(request)
    _prevent_auth_response_storage(response)
    try:
        user = confirm_registration(raw_token=data.token, password=data.password)
    except AccountOperationConflict as exc:
        raise HttpError(409, str(exc)) from exc
    except AccountOperationError as exc:
        raise HttpError(400, str(exc)) from exc

    access, refresh = issue_token_pair(user, device_name=data.device_name or "")
    _set_refresh_cookie(response, refresh)
    return BrowserRegistrationOutputSchema(
        detail="Email verified successfully.",
        access=access,
        email=user.email,
    )


@browser_auth_router.post(
    "/refresh",
    response={200: BrowserAccessTokenOutputSchema, 401: DetailResponse},
    throttle=[refresh_throttle],
)
def browser_refresh(
    request: HttpRequest, response: HttpResponse
) -> BrowserAccessTokenOutputSchema | Status[DetailResponse]:
    _require_csrf(request)
    _prevent_auth_response_storage(response)
    raw_refresh = request.COOKIES.get(settings.BROWSER_REFRESH_COOKIE_NAME)
    if not raw_refresh:
        _clear_refresh_cookie(response)
        return Status(401, DetailResponse(detail="Refresh session is unavailable"))

    try:
        access, refresh = rotate_token_pair(raw_refresh)
    except HttpError:
        _clear_refresh_cookie(response)
        return Status(401, DetailResponse(detail="Invalid or expired refresh token"))

    _set_refresh_cookie(response, refresh)
    return BrowserAccessTokenOutputSchema(access=access)


@browser_auth_router.post(
    "/logout", response=DetailResponse, throttle=[logout_throttle]
)
def browser_logout(request: HttpRequest, response: HttpResponse) -> DetailResponse:
    _require_csrf(request)
    _prevent_auth_response_storage(response)
    raw_refresh = request.COOKIES.get(settings.BROWSER_REFRESH_COOKIE_NAME)
    if raw_refresh:
        try:
            revoke_session_from_refresh(raw_refresh)
        except HttpError:
            # Logout is idempotent: an expired or already-revoked session still
            # results in the browser credential being removed.
            pass
    _clear_refresh_cookie(response)
    audit_logger.info("audit:browser_session_logged_out")
    return DetailResponse(detail="Logged out successfully.")
