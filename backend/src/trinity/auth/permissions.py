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


def permitted_dataset_keys(principal: Principal) -> tuple[str, ...]:
    """Return ordered internal dataset keys from the shared permission policy."""
    require(principal, "catalog:read")
    return ("national",) if principal.role == "viewer" else ("national", "facility", "generator")


def require_dataset(principal: Principal, dataset: str) -> None:
    """Hide both unknown and unauthorized dataset keys behind the same denial."""
    if dataset not in permitted_dataset_keys(principal):
        raise Problem(404, "dataset_not_found")
