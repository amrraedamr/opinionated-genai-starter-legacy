import json
import logging
import re
from datetime import UTC, datetime

from base.services.common.meta import scope_id

_SENSITIVE = re.compile(
    r"(?i)(api[_ -]?key|authorization|password|secret|token|prompt|response)"
    r"(\s*[:=]\s*)(['\"]?)([^'\"\s,}]+)\3"
)


def redact(value: str) -> str:
    return _SENSITIVE.sub(r"\1\2[REDACTED]", value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        try:
            request_id = str(scope_id.get())
        except LookupError:
            request_id = None
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)
