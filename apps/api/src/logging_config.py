import logging
import contextvars
from typing import Optional

# Context variable to hold current request trace id
trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None)


class TraceIdFilter(logging.Filter):
    """Logging filter that injects a `trace_id` attribute into LogRecords.

    The value is read from a contextvar so request handlers can set it and all
    log messages will include the same trace id.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        trace = trace_id_var.get(None)
        record.trace_id = trace or "-"
        return True


def configure_logging(level: int = logging.INFO) -> None:
    fmt = "%(asctime)s %(levelname)s [%(trace_id)s] %(name)s: %(message)s"
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(TraceIdFilter())
    root = logging.getLogger()
    if not root.handlers:
        root.setLevel(level)
        root.addHandler(handler)
