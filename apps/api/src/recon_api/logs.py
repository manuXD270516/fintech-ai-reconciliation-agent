from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

_RESERVED = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Tracebacks are reduced to the exception type."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            entry.update(fields)
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc_type"] = record.exc_info[0].__name__
        return json.dumps(entry, ensure_ascii=True, default=str)


def configure_logging(level: str = "INFO", stream: TextIO | None = None) -> None:
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers[:] = []
        uv_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("nats").setLevel(logging.CRITICAL)
