"""Read and write local identities using a service-owned transaction."""

import hashlib
import math
from uuid import uuid4

from trinity.auth.permissions import Principal, capabilities
from trinity.errors import Problem


def find_user(connection, username, *, lock=False):
    """Read a credential record without accepting client role claims."""
    return connection.execute("SELECT * FROM local_users WHERE username=%s" +
                              (" FOR UPDATE" if lock else ""), (username,)).fetchone()


def resolve_session(connection, token, *, lock=False):
    """Resolve current account authority, never a role copied into the session."""
    row = connection.execute("""
        SELECT s.id AS session_id, u.id AS user_id, u.role
        FROM local_sessions s JOIN local_users u ON u.id=s.user_id
        WHERE s.token_digest=%s AND s.revoked_at IS NULL
          AND s.expires_at>clock_timestamp() AND u.is_active
        """ + (" FOR UPDATE OF s" if lock else ""),
        (hashlib.sha256(token.encode("ascii")).hexdigest(),)).fetchone()
    if row is None:
        raise Problem(401, "invalid_session")
    capabilities(row["role"])
    return Principal(row["user_id"], row["role"], row["session_id"])


def create_session(connection, user_id, token):
    """Persist only the token digest and return the database-derived expiry."""
    return connection.execute("""
        WITH moment AS (SELECT clock_timestamp() AS now)
        INSERT INTO local_sessions(id,user_id,token_digest,created_at,expires_at)
        SELECT %s,%s,%s,now,now+interval '8 hours' FROM moment RETURNING expires_at
        """, (uuid4(), user_id, hashlib.sha256(token.encode("ascii")).hexdigest())).fetchone()["expires_at"]


def revoke_session(connection, session_id):
    """Revoke the already locked current session."""
    connection.execute("UPDATE local_sessions SET revoked_at=clock_timestamp() WHERE id=%s", (session_id,))


def reserve_login(connection, username, peer):
    """Reserve shared attempt counters before starting password work.

    The caller commits denied counters too. Lock the global row first to bound
    concurrent key creation and serialize the peer/username reservation.
    """
    keys = [("global", "all", 60), ("peer", peer, 30), ("username", username, 5)]
    for scope, key, limit in keys:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        connection.execute("""INSERT INTO auth_login_limits(scope,key_digest,window_start,attempts)
            VALUES (%s,%s,clock_timestamp(),0) ON CONFLICT DO NOTHING""", (scope, digest))
        row = connection.execute("""SELECT window_start,attempts,clock_timestamp() AS now
            FROM auth_login_limits WHERE scope=%s AND key_digest=%s FOR UPDATE""", (scope, digest)).fetchone()
        age = (row["now"] - row["window_start"]).total_seconds()
        if age >= 60:
            connection.execute("""UPDATE auth_login_limits SET window_start=clock_timestamp(),attempts=0
                WHERE scope=%s AND key_digest=%s""", (scope, digest))
            row["attempts"], age = 0, 0
        if row["attempts"] >= limit:
            return max(1, math.ceil(60 - age))
        connection.execute("UPDATE auth_login_limits SET attempts=attempts+1 WHERE scope=%s AND key_digest=%s",
                           (scope, digest))
    # This bounded cleanup cannot delete a live window or create unbounded work.
    connection.execute("""DELETE FROM auth_login_limits WHERE (scope,key_digest) IN (
        SELECT scope,key_digest FROM auth_login_limits
        WHERE window_start<clock_timestamp()-interval '120 seconds'
        ORDER BY window_start LIMIT 100)""")
    return None
