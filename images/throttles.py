import logging

from django.conf import settings
from ninja.throttling import UserRateThrottle


logger = logging.getLogger("audit")


class LoggingUserRateThrottle(UserRateThrottle):
    """User rate throttle that logs when a request is throttled (429)."""

    def allow_request(self, request, view=None):
        allowed = super().allow_request(request)
        if not allowed:
            user_id = getattr(getattr(request, "auth", None), "id", None)
            org = None
            try:
                parts = (request.path or "").split("/")
                if "orgs" in parts:
                    idx = parts.index("orgs")
                    org = parts[idx + 1] if len(parts) > idx + 1 else None
            except Exception:
                pass
            rate = getattr(self, "rate", None)
            remote = request.META.get("REMOTE_ADDR") if hasattr(request, "META") else None
            logger.warning(
                "audit:rate_limited user=%s org=%s path=%s rate=%s ip=%s",
                user_id,
                org,
                getattr(request, "path", None),
                rate,
                remote,
            )
        return allowed


upload_throttle = LoggingUserRateThrottle(getattr(settings, "IMAGES_RATE_LIMIT_UPLOAD", "60/h"))
bulk_upload_throttle = LoggingUserRateThrottle(getattr(settings, "IMAGES_RATE_LIMIT_BULK_UPLOAD", "30/h"))
bulk_delete_throttle = LoggingUserRateThrottle(getattr(settings, "IMAGES_RATE_LIMIT_BULK_DELETE", "30/h"))
bulk_attach_throttle = LoggingUserRateThrottle(getattr(settings, "IMAGES_RATE_LIMIT_BULK_ATTACH", "60/h"))
bulk_detach_throttle = LoggingUserRateThrottle(getattr(settings, "IMAGES_RATE_LIMIT_BULK_DETACH", "60/h"))
