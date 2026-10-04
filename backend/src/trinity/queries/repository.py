"""Persist rate debits and lifecycle ownership in service-owned transactions."""

from datetime import timedelta
import math
from uuid import uuid4
from trinity.errors import Problem


def reserve_rate(connection, user_id):
    """Return Retry-After on denial; preserve a bounded rolling DB-time window."""
    connection.execute("INSERT INTO analytical_rate_limits(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (user_id,))
    row = connection.execute("SELECT admitted_at,last_time FROM analytical_rate_limits WHERE user_id=%s FOR UPDATE",
                             (user_id,)).fetchone()
    now = connection.execute("SELECT greatest(clock_timestamp(),%s) AS now", (row['last_time'],)).fetchone()['now']
    recent = [t for t in row['admitted_at'] if t > now - timedelta(seconds=60)]
    if len(recent) >= 30:
        return max(1, math.ceil((recent[0] + timedelta(seconds=60) - now).total_seconds()))
    connection.execute("UPDATE analytical_rate_limits SET admitted_at=%s,last_time=%s WHERE user_id=%s",
                       (recent + [now], now, user_id))
    return None


def reserve_capacity(connection, user_id, pinned, deployment_id, daemon_id, seconds):
    """Return a reservation only below both limits under the singleton lock."""
    if connection.execute("SELECT id FROM query_admission WHERE id=1 FOR UPDATE").fetchone() is None:
        raise Problem(503, 'dependency_unavailable')
    row = connection.execute("""SELECT count(*) AS total,
        count(*) FILTER (WHERE user_id=%s) AS per_user FROM query_reservations WHERE state<>'released'""",
        (user_id,)).fetchone()
    if row['total'] >= 4 or row['per_user'] >= 2:
        return None
    request, owner = uuid4(), uuid4()
    publication = pinned.publication
    return connection.execute("""INSERT INTO query_reservations(request_id,user_id,publication_event_id,
        version_id,manifest_sha256,deployment_id,daemon_id,owner_token,state,container_name,deadline)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'reserved',%s,clock_timestamp()+%s*interval '1 second') RETURNING *""",
        (request,user_id,publication.publication_event_id,publication.version_id,pinned.manifest_sha256,
         deployment_id,daemon_id,owner,'trinity-query-'+str(request),seconds)).fetchone()


def transition(connection, reservation, expected, state, *, container_id=None):
    """Advance only the current owner's expected state; record immutable IDs."""
    row = connection.execute("""UPDATE query_reservations SET state=%s,
        container_id=COALESCE(container_id,%s), start_intent=start_intent OR %s,
        heartbeat_at=clock_timestamp()
        WHERE request_id=%s AND owner_token=%s AND generation=%s AND state=ANY(%s)
          AND (container_id IS NULL OR %s::text IS NULL OR container_id=%s)
          AND (deadline>clock_timestamp() OR %s IN ('stopping','cleaning')) RETURNING *""",
        (state,container_id,state=='starting',reservation['request_id'],reservation['owner_token'],
         reservation['generation'],list(expected),container_id,container_id,state)).fetchone()
    if row is None:
        raise Problem(503, 'dependency_unavailable')
    return row


def release_unlaunched(connection, reservation, outcome):
    """Release only states that cannot have issued a Docker create/start."""
    return connection.execute("""UPDATE query_reservations SET state='released',outcome=%s,
        cleanup_complete=true,released_at=clock_timestamp() WHERE request_id=%s AND owner_token=%s
        AND generation=%s AND state IN ('reserved','staging') AND container_id IS NULL
        AND NOT start_intent RETURNING request_id""",
        (outcome,reservation['request_id'],reservation['owner_token'],reservation['generation'])).fetchone() is not None


def release_removed(connection, reservation, outcome):
    """Release after the caller proves removal of the immutable container ID."""
    return connection.execute("""UPDATE query_reservations SET state='released',outcome=%s,
        cleanup_complete=true,released_at=clock_timestamp() WHERE request_id=%s AND owner_token=%s
        AND generation=%s AND state='cleaning' AND container_id IS NOT NULL RETURNING request_id""",
        (outcome,reservation['request_id'],reservation['owner_token'],reservation['generation'])).fetchone() is not None


def claim_expired(connection, deployment_id):
    """Fence one expired reservation; expiry itself never releases capacity."""
    return connection.execute("""UPDATE query_reservations SET owner_token=%s,generation=generation+1,
        heartbeat_at=clock_timestamp(),deadline=clock_timestamp()+interval '10 seconds'
        WHERE request_id=(SELECT request_id FROM query_reservations
            WHERE deployment_id=%s AND state<>'released' AND deadline<clock_timestamp()
            ORDER BY deadline FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *""", (uuid4(),deployment_id)).fetchone()
