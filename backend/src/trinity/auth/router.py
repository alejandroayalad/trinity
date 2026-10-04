"""Expose local login/logout and current application entry state."""
from fastapi import APIRouter, Depends, Request, Response
from trinity.auth.dependencies import authenticated, bearer_token
from trinity.auth.schemas import EmptyRequest, LoginRequest, LoginResponse, MeResponse

router = APIRouter(prefix="/api/v1")


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request):
    """Verify local credentials without trusting forwarded peer headers."""
    peer = request.client.host if request.client else "unknown"
    return request.app.state.auth.login(body.username, body.password.get_secret_value(), peer)


@router.post("/auth/logout", status_code=204)
def logout(body: EmptyRequest, request: Request, token=Depends(bearer_token)):
    """Revoke the current session before returning an empty success response."""
    request.app.state.auth.logout(token)
    return Response(status_code=204)


@router.get("/me", response_model=MeResponse)
def me(request: Request, context=Depends(authenticated, scope="function")):
    """Return identity and role-aware readiness from one database snapshot."""
    return request.app.state.auth.me(*context)
