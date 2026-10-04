"""Authenticate local users and assemble authorized app-entry responses."""

from contextlib import contextmanager
import secrets
import psycopg

from trinity.adapters.postgres import Deadline
from trinity.auth import repository
from trinity.auth.passwords import hash_password, verify_password
from trinity.auth.permissions import capabilities
from trinity.auth.schemas import LoginResponse, MeResponse
from trinity.errors import Problem
from trinity.publication.repository import read_publication
from trinity.refresh.repository import read_context
from trinity.refresh.service import admin_context
from trinity.settings.repository import read_settings


class AuthService:
    """Verify credentials, commit sessions and read current role-aware app state.

    Receives trusted database access, never client-supplied actors or roles.
    A failed persistence step grants no successful login/logout response.
    """

    def __init__(self, database):
        self.database = database
        try:
            self.dummy_hash = hash_password(secrets.token_urlsafe(32))
        except Exception:
            raise RuntimeError("Password verification is unavailable.") from None

    def login(self, username, password, peer):
        """Commit a new session only after current active credentials verify."""
        deadline = Deadline()
        with self.database.transaction(deadline) as connection:
            retry = repository.reserve_login(connection, username, peer)
        if retry is not None:
            raise Problem(429, "rate_limited", retry_after=retry)
        with self.database.transaction(deadline, readonly=True) as connection:
            user = repository.find_user(connection, username)
        encoded = user["password_hash"] if user and user["is_active"] else self.dummy_hash
        verified = verify_password(password, encoded, deadline)
        if not verified or not user or not user["is_active"]:
            raise Problem(401, "invalid_credentials")
        capabilities(user["role"])
        token = secrets.token_urlsafe(32)
        with self.database.transaction(deadline) as connection:
            current = repository.find_user(connection, username, lock=True)
            if (not current or not current["is_active"] or current["id"] != user["id"]
                    or current["password_hash"] != encoded):
                raise Problem(401, "invalid_credentials")
            capabilities(current["role"])
            expires = repository.create_session(connection, current["id"], token)
        return LoginResponse(access_token=token, expires_at=expires)

    @contextmanager
    def authenticated(self, token):
        """Share one read snapshot between identity and authorized app state."""
        with self.database.transaction(Deadline(), readonly=True) as connection:
            principal = repository.resolve_session(connection, token)
            try:
                yield principal, connection
            except psycopg.Error:
                raise Problem(503, "dependency_unavailable") from None

    def logout(self, token):
        """Persist revocation before reporting success."""
        with self.database.transaction(Deadline()) as connection:
            principal = repository.resolve_session(connection, token, lock=True)
            repository.revoke_session(connection, principal.session_id)

    def me(self, principal, connection):
        """Return readiness only from the active publication snapshot."""
        publication = read_publication(connection)
        context = None
        landing = "waiting"
        if publication:
            landing = "national_dashboard" if principal.role == "viewer" else "explorer"
        if principal.role == "admin":
            settings = read_settings(connection)
            context = admin_context(settings, *read_context(connection))
            if not context.setup_completed:
                landing = "setup"
            elif publication is None:
                landing = "refresh_runs"
        return MeResponse(user_id=principal.user_id, role=principal.role,
                          capabilities=list(capabilities(principal.role)),
                          data_ready=publication is not None, publication=publication,
                          landing_screen=landing, admin_context=context)
