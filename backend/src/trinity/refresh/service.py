"""Derive app-entry actions from retained lifecycle evidence."""
from trinity.auth.schemas import Action, AdminContext, Blocker, RefreshSummary


def _authorize(connection, token, capability, *, lock=False):
    """Recheck the current session and role; optional locks protect command effects."""
    import psycopg
    from trinity.auth.repository import resolve_session
    from trinity.auth.permissions import require
    from trinity.errors import Problem
    try:
        principal = resolve_session(connection,token)
        require(principal,capability)
        if lock:
            # Holding the user and session rows prevents a concurrent role
            # change or logout from crossing this command's commit boundary.
            connection.execute('SELECT id FROM local_users WHERE id=%s FOR SHARE',(principal.user_id,))
            principal = resolve_session(connection,token,lock=True)
            require(principal,capability)
        return principal
    except psycopg.Error:
        raise Problem(503,'auth_unavailable') from None


def _receipt(row, *, replayed):
    """Project the immutable acceptance fields, never substitute current run state."""
    from trinity.refresh.schemas import ActionReceipt
    return ActionReceipt(operation_id=row['id'],action=row['action'],accepted_at=row['accepted_at'],
        run_id=row['run_id'],version_id=row['version_id'],status_url=row['status_url'],
        result=row['result'],replayed=replayed)


class RefreshService:
    """Accept Admin intent atomically and read bounded tracking snapshots.

    Input is a bearer token plus raw command or paging input. Resolve current
    authority before reading protected state. Commands use a writable database
    transaction; tracking reads use one read-only snapshot. Only PostgreSQL is
    involved. Return acceptance after commit; any write or commit failure leaves
    no run, slot, outbox obligation or receipt from that request.
    """
    def __init__(self, database, *, codec_factory=None):
        from trinity.refresh.cursors import RefreshCursorCodec, load_refresh_keys
        self.database = database
        self.codec_factory = codec_factory or (lambda:RefreshCursorCodec(load_refresh_keys()))

    def start(self, token, raw, key_headers, pairs=()):
        """Reserve one full refresh or return its authorized original receipt."""
        from trinity.adapters.postgres import Deadline
        from trinity.contracts.manifest import canonical_json, sha256
        from trinity.errors import Problem
        from trinity.refresh import repository
        from trinity.refresh.schemas import parse_command
        from trinity.settings.repository import read_settings
        fingerprint = sha256(canonical_json({}))
        try:
            with self.database.transaction(Deadline(),error_code='dependency_unavailable') as connection:
                _authorize(connection,token,'refresh:start')
                key = parse_command(raw,key_headers,pairs)
                repository.lock_control(connection)
                actor = _authorize(connection,token,'refresh:start',lock=True)
                previous = repository.read_command(connection,key)
                if previous is not None:
                    if (previous['actor_id']!=actor.user_id or previous['action']!='start_refresh'
                            or previous['target_id'] is not None or previous['request_fingerprint']!=fingerprint):
                        raise Problem(409,'idempotency_conflict')
                    result = _receipt(previous,replayed=True)
                else:
                    # Settings cannot change between the guard and its frozen
                    # snapshot. Replay intentionally did not need this guard.
                    connection.execute('SELECT id FROM shared_settings WHERE id=1 FOR SHARE')
                    settings = read_settings(connection)
                    run,version,warning,approval,step = repository.read_context(connection)
                    context = admin_context(settings,run,version,warning,approval,step)
                    if not context.setup_completed:
                        raise Problem(409,'setup_required',blocker=context.refresh_blocker.model_dump(mode='json'))
                    if context.refresh_blocker is not None:
                        raise Problem(409,'refresh_blocked',blocker=context.refresh_blocker.model_dump(mode='json'))
                    result = _receipt(repository.accept_run(connection,actor.user_id,key,fingerprint,settings),replayed=False)
            # Exiting the transaction can still fail at commit. Never return
            # this object to the HTTP adapter from inside that context manager.
            return result
        except Problem as error:
            if error.status==503 and error.code=='dependency_unavailable':
                raise Problem(503,error.code,retry_after=1) from None
            raise

    def _page(self, pairs, body, *, run_id=None):
        """Load signing keys only when decoding or emitting a continuation."""
        from trinity.refresh.schemas import parse_page
        limit,token = parse_page(pairs,steps=run_id is not None,body=body)
        purpose = 'refresh-steps' if run_id is not None else 'refresh-history'
        target = str(run_id) if run_id is not None else None
        codec = self.codec_factory() if token is not None else None
        position = codec.decode(token,purpose=purpose,target=target,limit=limit) if codec else None
        return (position['limit'] if position else limit or (100 if run_id is not None else 20),
                position,codec,purpose,target)

    def _next(self, rows, maximum, page, field):
        """Create a cursor only when the measured extra row proves another page."""
        limit,position,codec,purpose,target = page
        if len(rows)<=limit:
            return None
        codec = codec or self.codec_factory()
        return codec.encode(purpose=purpose,target=target,limit=limit,maximum=maximum,after=rows[limit-1][field])

    def history(self, token, pairs=(), *, body=b''):
        """Read stable history and fresh current admission context in one snapshot."""
        from trinity.adapters.postgres import Deadline
        from trinity.refresh import repository
        from trinity.refresh.schemas import RunList
        from trinity.refresh.tracking import summary, warning_view
        from trinity.settings.repository import read_settings
        with self.database.transaction(Deadline(),readonly=True,error_code='dependency_unavailable') as connection:
            _authorize(connection,token,'refresh:read')
            page = self._page(pairs,body)
            limit,position,*_ = page
            rows,maximum = repository.run_history(connection,position['maximum'] if position else None,
                                                  position['after'] if position else None,limit)
            state = repository.read_context(connection)
            context = admin_context(read_settings(connection),*state)
            return RunList(items=[summary(row) for row in rows[:limit]],next_cursor=self._next(rows,maximum,page,'run_seq'),
                active_run=context.active_run,unresolved_warning=warning_view(state[2]),
                blocker=context.refresh_blocker,actions=context.actions)

    def detail(self, token, run_id, pairs=(), *, body=b''):
        """Read current run state while paging only its retained step history."""
        from uuid import UUID
        from trinity.adapters.postgres import Deadline
        from trinity.errors import Problem
        from trinity.refresh import repository
        from trinity.refresh.tracking import run_view
        from trinity.settings.repository import read_settings
        with self.database.transaction(Deadline(),readonly=True,error_code='dependency_unavailable') as connection:
            _authorize(connection,token,'refresh:read')
            try:
                identifier = UUID(run_id)
                if str(identifier)!=run_id.lower():raise ValueError
            except (ValueError,TypeError,AttributeError):
                raise Problem(422,'invalid_request') from None
            page = self._page(pairs,body,run_id=identifier)
            limit,position,*_ = page
            detail = repository.run_detail(connection,identifier)
            rows,maximum = repository.run_steps(connection,identifier,position['maximum'] if position else None,
                                                position['after'] if position else None,limit)
            state = repository.read_context(connection)
            context = admin_context(read_settings(connection),*state)
            return run_view(detail,rows[:limit],self._next(rows,maximum,page,'step_seq'),context)


def admin_context(settings, run, version, warning, approval, step):
    """Describe eligibility without granting permission to publish or recover."""
    setup = settings["setup_completed_at"] is not None
    status = run["status"] if run else None
    code = None
    if not setup:
        code = "setup_required"
    elif status in ("requested", "running"):
        code = "refresh_active"
    elif status == "awaiting_approval":
        code = "review_required"
    elif status == "publishing":
        code = "publication_in_progress"
    elif status in ("failed", "publication_failed"):
        code = "failure_unresolved"
    publication_actions = run.get('_publication_actions', {}) if run else {}
    enabled = {
        "start_refresh": setup and run is None,
        "rerun": False,
        "delete_warning": False,
        **{name: setup and publication_actions.get(name,False)
           for name in ('approve','publication_retry','discard')},
    }
    actions = [Action(action=name, enabled=bool(allowed),
                      reason_code=None if allowed else (code or "not_applicable"))
               for name, allowed in enabled.items()]
    blocker = Blocker(code=code, message="Complete setup or resolve the current refresh.",
                      run_id=run["id"] if run else None, version_id=version["id"] if version else None,
                      warning_id=warning["id"] if warning else None) if code else None
    summary = RefreshSummary(run_id=run["id"], status=run["status"], requested_at=run["requested_at"],
                             finished_at=run["finished_at"]) if run else None
    return AdminContext(setup_completed=setup, refresh_blocker=blocker, active_run=summary, actions=actions)
