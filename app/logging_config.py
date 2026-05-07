import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

LOG_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"

_cache = {}


def _make_handler(filepath, level=logging.DEBUG):
    handler = RotatingFileHandler(filepath, maxBytes=5_000_000, backupCount=10)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FMT, datefmt=DATE_FMT))
    return handler


def setup_per_call_logger(call_id: str) -> logging.Logger:
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{now}_{call_id}.log"
    filepath = os.path.join(LOGS_DIR, filename)

    logger_name = f"call.{call_id}"
    log = logging.getLogger(logger_name)
    log.setLevel(logging.DEBUG)

    if logger_name not in _cache:
        log.addHandler(_make_handler(filepath))
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(LOG_FMT, datefmt=DATE_FMT))
        log.addHandler(console)
        _cache[logger_name] = True

    return log


def get_active_logger(component: str) -> logging.Logger:
    call_id = _get_current_call_id()
    return setup_per_call_logger(call_id)


def get_call_logger(call_id: str) -> logging.Logger:
    return setup_per_call_logger(call_id)


def _get_current_call_id() -> str:
    try:
        from flask import has_request_context, g
        if has_request_context():
            return getattr(g, "call_id", "no-request")
    except Exception:
        pass
    return "no-request"


def setup_root_logger():
    root_log = logging.getLogger("app")
    root_log.setLevel(logging.DEBUG)

    if not root_log.handlers:
        main_path = os.path.join(LOGS_DIR, "app.log")
        root_log.addHandler(_make_handler(main_path))
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(LOG_FMT, datefmt=DATE_FMT))
        root_log.addHandler(console)

    return root_log
