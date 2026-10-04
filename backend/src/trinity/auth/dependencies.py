"""Authenticate protected routes before their service reads application state."""

import re
from fastapi import Request
from trinity.auth.permissions import require
from trinity.errors import Problem


def bearer_token(request: Request) -> str:
    """Accept one bounded opaque Bearer token, never query/cookie authority."""
    headers = request.headers.getlist("authorization")
    if not headers:
        raise Problem(401, "authentication_required")
    if len(headers) != 1 or len(headers[0]) > 4103:
        raise Problem(401, "invalid_session")
    match = re.fullmatch(r"(?i:Bearer) ([A-Za-z0-9_-]{43})", headers[0])
    if not match:
        raise Problem(401, "invalid_session")
    return match.group(1)


def authenticated(request: Request):
    """Keep identity and app-state reads inside one shared transaction."""
    token = bearer_token(request)
    with request.app.state.auth.authenticated(token) as context:
        yield context


def require_capability(capability: str):
    """Build a reusable HTTP guard using the production permission policy."""
    from fastapi import Depends

    def dependency(context=Depends(authenticated, scope="function")):
        require(context[0], capability)
        return context

    return dependency
