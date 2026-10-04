"""Define the single role and dataset policy used by protected features."""

from dataclasses import dataclass
from trinity.errors import Problem

VIEWER = ("national:read", "catalog:read", "preview:national")
ANALYST = VIEWER + ("preview:detail", "sql:execute")
ADMIN = ANALYST + ("settings:read", "settings:write", "refresh:read", "refresh:start",
                   "refresh:recover", "candidate:review")
CAPABILITIES = {"viewer": VIEWER, "analyst": ANALYST, "admin": ADMIN}


@dataclass(frozen=True)
class Principal:
    """Hold an identity obtained only from current trusted application state."""
    user_id: str
    role: str
    session_id: object


def capabilities(role: str) -> tuple[str, ...]:
    """Deny unknown roles rather than giving a default permission level."""
    if role not in CAPABILITIES:
        raise Problem(403, "forbidden")
    return CAPABILITIES[role]


def require(principal: Principal, capability: str) -> None:
    """Authorize the operation before looking up its protected resources."""
    if capability not in capabilities(principal.role):
        raise Problem(403, "forbidden")


def require_dataset(principal: Principal, dataset: str) -> None:
    """Hide both unknown and unauthorized dataset keys behind the same denial."""
    require(principal, "catalog:read")
    permitted = ("national",) if principal.role == "viewer" else ("national", "facility", "generator")
    if dataset not in permitted:
        raise Problem(404, "dataset_not_found")
