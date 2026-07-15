import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JSONFormatter(logging.Formatter):
    """Minimal JSON log formatter suitable for shipping to stdout.

    Usage: set as formatter for handlers; includes level, logger, message, timestamp,
    and selected audit-context extras when present.
    """

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id:
            data["request_id"] = request_id
        # Include common audit context keys if found in the message via extra fields
        # If developers pass extra={"org": ..., "user": ...}, include them
        for key in (
            "event",
            "org",
            "user",
            "method",
            "path",
            "access",
            "app",
            "model",
            "obj",
            "image",
            "tag_id",
            "attached",
            "detached",
            "tags",
            "rel",
        ):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            data["stack"] = self.formatStack(record.stack_info)
        # Include pathname:lineno for debugging
        data["src"] = f"{record.pathname}:{record.lineno}"
        return json.dumps(data, ensure_ascii=False)
