"""Structured JSON logs with request/job ids. Never log secrets or learner code."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_STD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}
_REDACT = ("key", "token", "secret", "password", "authorization", "source_code")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            data["request_id"] = rid
        for k, v in record.__dict__.items():
            if k in _STD or k.startswith("_"):
                continue
            data[k] = "[redacted]" if any(r in k.lower() for r in _REDACT) else v
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel("WARNING")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if incoming.isalnum() and len(incoming) <= 64 else uuid.uuid4().hex[:16]
        request.state.request_id = rid
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = rid
        if request.url.path.startswith("/api/") and request.method != "GET":
            logging.getLogger("mlforge.http").info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                    "request_id": rid,
                },
            )
        return response
