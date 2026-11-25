"""Structured JSON logs. Personal data and secrets are never passed to the logger."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_STANDARD = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "taskName",
    "color_message",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in _STANDARD})
        if record.exc_info and record.exc_info[0]:
            # Exception messages can quote user input, so only the type and place are logged.
            payload["error_type"] = record.exc_info[0].__name__
            tb = record.exc_info[2]
            frames = []
            while tb:
                frames.append(f"{tb.tb_frame.f_code.co_filename}:{tb.tb_lineno}")
                tb = tb.tb_next
            payload["trace"] = frames[-6:]
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = name != "uvicorn.access"
    logging.getLogger("httpx").setLevel(logging.WARNING)
