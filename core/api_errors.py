import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from ninja.errors import HttpError, ValidationError

from core.error_reporting import report_exception

logger = logging.getLogger(__name__)


def validation_error_response(
    request: HttpRequest, exc: ValidationError | type[ValidationError]
) -> HttpResponse:
    error_items = exc.errors if isinstance(exc, ValidationError) else []
    errors = [
        {
            "location": list(item.get("loc", ())),
            "message": str(item.get("msg", "Invalid value")),
            "type": str(item.get("type", "validation_error")),
        }
        for item in error_items
    ]
    messages = [str(item.get("msg", "Invalid value")) for item in error_items]
    detail = "; ".join(messages) or "Request validation failed."
    return JsonResponse({"detail": detail, "errors": errors}, status=400)


def http_error_response(
    request: HttpRequest, exc: HttpError | type[HttpError]
) -> HttpResponse:
    return JsonResponse(
        {"detail": str(exc)},
        status=getattr(exc, "status_code", 400),
    )


def unhandled_error_response(
    request: HttpRequest, exc: Exception | type[Exception]
) -> HttpResponse:
    if isinstance(exc, type):
        exc = exc()
    request_id = getattr(request, "request_id", None)
    context = {
        "request_id": request_id,
        "method": request.method,
        "path": request.path,
    }
    logger.error(
        "Unhandled API exception",
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    report_exception(exc, context=context)
    payload = {"detail": "Internal server error."}
    if request_id:
        payload["request_id"] = request_id
    return JsonResponse(payload, status=500)
