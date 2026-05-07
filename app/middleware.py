import uuid
import time
import logging
from flask import request, g

from app.logging_config import setup_per_call_logger

logger = logging.getLogger("app.middleware")


def register_request_logging(app):
    @app.before_request
    def before_request_log():
        call_id = str(uuid.uuid4())[:8]
        g.call_id = call_id
        g.request_start = time.time()

        body = None
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = request.get_json(silent=True)
            except Exception:
                body = "<unreadable>"

        log = setup_per_call_logger(call_id)
        g.call_logger = log

        log.info(
            f"REQUEST START | {request.method} {request.path} | "
            f"ip={request.remote_addr} | query_params={dict(request.args)} | "
            f"body={body}"
        )
        logger.info(f"[{call_id}] {request.method} {request.path}")

    @app.after_request
    def after_request_log(response):
        duration = round((time.time() - getattr(g, "request_start", time.time())) * 1000, 1)
        call_logger = getattr(g, "call_logger", None)

        if call_logger:
            call_logger.info(
                f"REQUEST END | status={response.status_code} | duration={duration}ms | "
                f"method={request.method} | path={request.path}"
            )
        logger.info(f"[{getattr(g, 'call_id', '?')}] {response.status_code} in {duration}ms")
        return response

    @app.teardown_request
    def teardown_request_log(exception):
        if exception:
            call_logger = getattr(g, "call_logger", None)
            if call_logger:
                call_logger.error(f"REQUEST EXCEPTION | {request.method} {request.path} | error={exception}")
            logger.error(f"[{getattr(g, 'call_id', '?')}] Exception: {exception}")


def get_current_call_id() -> str:
    try:
        from flask import has_request_context, g
        if has_request_context():
            return getattr(g, "call_id", "no-request")
    except Exception:
        pass
    return "no-request"
