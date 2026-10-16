"""Stdlib logging in ``key=value`` (logfmt) format.

Context travels in ``extra=`` (``payment_id``, ``event_id``, ...) rather than being
interpolated into the message, so log lines stay grep- and parser-friendly.
"""

import json
import logging
from datetime import UTC, datetime

_STANDARD_ATTRS = frozenset(
    {*vars(logging.LogRecord("", 0, "", 0, "", None, None)), "message", "asctime"}
)


def _value(value: object) -> str:
    text = str(value)
    if not text or any(ch in text for ch in ' "=\n\t'):
        return json.dumps(text, ensure_ascii=False)
    return text


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
        }
        line = " ".join(f"{key}={_value(value)}" for key, value in fields.items())
        line += f" msg={json.dumps(record.getMessage(), ensure_ascii=False)}"
        context = {k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS}
        if context:
            line += " " + " ".join(f"{key}={_value(value)}" for key, value in context.items())
        if record.exc_info:
            line += f" exc={_value(self.formatException(record.exc_info))}"
        return line


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(KeyValueFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
