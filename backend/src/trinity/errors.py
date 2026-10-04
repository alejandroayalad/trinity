"""Map API failures to bounded public problems without exposing raw exceptions."""

import asyncio
from http import HTTPStatus
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class Problem(Exception):
    """Carry only a trusted error code and status, never an exception message."""

    def __init__(self, status: int, code: str, *, retry_after: int | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.retry_after = retry_after


def problem_response(error: Problem, request_id: str, errors: list | None = None) -> JSONResponse:
    """Build the canonical safe error envelope."""
    title = HTTPStatus(error.status).phrase
    headers = {"Cache-Control": "no-store", "X-Request-ID": request_id}
    if error.status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    if error.retry_after is not None:
        headers["Retry-After"] = str(max(1, error.retry_after))
    return JSONResponse({
        "type": "about:blank", "title": title, "status": error.status,
        "detail": title, "code": error.code, "request_id": request_id,
        "errors": errors or [], "blocker": None, "current_revision": None,
    }, status_code=error.status, media_type="application/problem+json", headers=headers)


def install_handlers(app) -> None:
    """Install handlers that exclude rejected values and raw exception text."""
    @app.exception_handler(Problem)
    async def domain_error(request: Request, exc: Problem):
        return problem_response(exc, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Error locations can contain attacker-supplied field names; allow known fields only.
        fields = {"username", "password"}
        errors = [{"field": str(e["loc"][-1]) if e["loc"] and e["loc"][-1] in fields else "body",
                   "code": "invalid", "message": "Invalid field."} for e in exc.errors()[:20]]
        code = "invalid_json" if any(e["type"] == "json_invalid" for e in exc.errors()) else "invalid_request"
        return problem_response(Problem(400 if code == "invalid_json" else 422, code),
                                request.state.request_id, errors)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = "resource_not_found" if exc.status_code == 404 else "invalid_request"
        return problem_response(Problem(exc.status_code, code), request.state.request_id)


class SafeTransport:
    """Bound JSON input and contain unexpected failures before sending a response.

    Bodies are small and buffered once. No request body, query or authorization
    header is recorded, and an incoming request ID is never trusted.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        sent = False

        async def safe_send(message):
            nonlocal sent
            if message["type"] == "http.response.start":
                sent = True
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() not in (b"cache-control", b"x-request-id")]
                headers += [(b"cache-control", b"no-store"), (b"x-request-id", request_id.encode())]
                message = {**message, "headers": headers}
            await send(message)

        try:
            body = bytearray()
            async with asyncio.timeout(5):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > 65536:
                        raise Problem(413, "request_too_large")
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
            if scope.get("query_string"):
                raise Problem(422, "invalid_request")
            if scope["method"] == "GET" and body:
                raise Problem(422, "invalid_request")
            if scope["method"] == "POST":
                headers = [v for k, v in scope["headers"] if k.lower() == b"content-type"]
                if len(headers) != 1 or headers[0].split(b";", 1)[0].strip().lower() != b"application/json":
                    raise Problem(415, "unsupported_media_type")
            consumed = False

            async def replay():
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay, safe_send)
        except Exception as exc:
            if sent:
                raise
            error = exc if isinstance(exc, Problem) else Problem(500, "internal_error")
            if isinstance(exc, TimeoutError):
                error = Problem(422, "invalid_request")
            await problem_response(error, request_id)(scope, receive, safe_send)
