"""Supervise query staging, fenced container execution and durable cleanup."""
import json
from pathlib import Path
import time

from trinity.adapters.docker import read_frames
from trinity.contracts.manifest import read_json
from trinity.errors import Problem
from trinity.contracts.queries import PreviewOperation, read_result_binding
from trinity.contracts.choices import ChoiceOperation
from trinity.queries.choice_schemas import build_choice_response
from trinity.publication.diagnostics import read_preview_diagnostics
from trinity.queries.preview_schemas import build_preview_batch_response
from trinity.queries import repository
from trinity.queries.schemas import QueryResponse
from trinity.queries.service import QueryDeadline
from trinity.queries.staging import stage_query, StagedQuery


class QueryExecution:
    """Hold trusted deployment configuration; no request controls Docker or S3."""
    def __init__(self,database,docker,reader,root,deployment_id,*,evidence_cache=None,evidence_namespace=()):
        self.database,self.docker,self.reader,self.root=database,docker,reader,Path(root)
        self.deployment_id,self.daemon_id=deployment_id,docker.daemon_id
        self.evidence_cache,self.evidence_namespace=evidence_cache,evidence_namespace

    def close(self):
        """Close trusted transports after success, denial or recovery work."""
        self.docker.client.close()
        if self.reader is not None and hasattr(self.reader.client, 'close'):
            self.reader.client.close()

    def change(self,reservation,expected,state,*,container_id=None):
        with self.database.transaction(QueryDeadline(10),error_code='dependency_unavailable') as connection:
            return repository.transition(connection,reservation,expected,state,container_id=container_id)

    def cleanup(self,reservation,outcome):
        """Retain ambiguous creates; release only after known-safe local cleanup."""
        staged=StagedQuery(self.root / str(reservation['request_id']),str(reservation['request_id']))
        if reservation['state'] in ('reserved','staging'):
            with self.database.transaction(QueryDeadline(10),error_code='dependency_unavailable') as connection:
                owned=connection.execute("""SELECT request_id FROM query_reservations
                    WHERE request_id=%s AND owner_token=%s AND generation=%s
                    AND state IN ('reserved','staging') AND container_id IS NULL AND NOT start_intent
                    FOR UPDATE""",(reservation['request_id'],reservation['owner_token'],reservation['generation'])).fetchone()
                if owned is None:raise Problem(503,'dependency_unavailable')
            staged.cleanup()
            with self.database.transaction(QueryDeadline(10),error_code='dependency_unavailable') as connection:
                if not repository.release_unlaunched(connection,reservation,outcome):raise Problem(503,'dependency_unavailable')
            return
        if reservation['container_id'] is None:
            info=self.docker.inspect(reservation['container_name'])
            if info is None:raise Problem(503,'dependency_unavailable')
            labels=info.get('Config',{}).get('Labels',{})
            if (labels.get('trinity.query')!=str(reservation['request_id'])
                    or labels.get('trinity.deployment')!=str(reservation['deployment_id'])):
                raise Problem(503,'dependency_unavailable')
            reservation=self.change(reservation,(reservation['state'],),'stopping',container_id=info['Id'])
        else:
            reservation=self.change(reservation,(reservation['state'],),'stopping')
        self.docker.remove_stopped(reservation['container_id'],reservation)
        reservation=self.change(reservation,('stopping',),'cleaning')
        staged.cleanup()
        with self.database.transaction(QueryDeadline(10),error_code='dependency_unavailable') as connection:
            if not repository.release_removed(connection,reservation,outcome):raise Problem(503,'dependency_unavailable')

    def execute(self, prepared):
        """Run a prepared operation and return its response after owned cleanup.

        The service supplies an authorized operation, a pinned publication,
        a capacity reservation and a deadline. Stage the published files, run
        the isolated container, and check that its output matches this request.
        Build a SQL, preview or choice response within the size and time limits.

        Always attempt cleanup and close the transports before returning.
        Cleanup retains capacity when it cannot prove that release is safe.
        Query failures keep their public error codes. Unexpected execution
        errors become dependency_unavailable. Cleanup errors prevent success.
        Authorization and capacity admission belong to the calling service.
        """
        reservation = prepared.reservation
        attached = None
        outcome = 'dependency_unavailable'
        try:
            # Record ownership before reading evidence or staging files. Preview
            # needs verified diagnostics from the same pinned publication.
            reservation = self.change(reservation, ('reserved',), 'staging')
            diagnostics = None
            if isinstance(prepared.query, PreviewOperation):
                # Reuse only verified evidence. This reservation still owns its
                # staging and container work while a shared cache fill is pending.
                if self.evidence_cache is None:
                    diagnostics = read_preview_diagnostics(
                        prepared.pinned,
                        prepared.query.dataset,
                        self.reader,
                        prepared.deadline,
                    )
                else:
                    diagnostics = self.evidence_cache.read(
                        prepared.pinned,
                        prepared.query.dataset,
                        self.reader,
                        prepared.deadline,
                        namespace=self.evidence_namespace,
                    )
            stage_query(
                self.root,
                reservation['request_id'],
                prepared.pinned,
                prepared.query,
                self.reader,
                prepared.deadline,
            )

            # Save create intent before calling Docker. If the reply is lost,
            # cleanup must resolve the container before releasing capacity.
            reservation = self.change(reservation, ('staging',), 'creating')
            identifier = self.docker.create(reservation)
            reservation = self.change(
                reservation, ('creating',), 'created', container_id=identifier,
            )
            info = self.docker.inspect(identifier)
            self.docker.verify(info, reservation)

            # Attach before starting so output is available from the first byte.
            # Save start intent before Docker can begin running the query.
            attached, stream = self.docker.attach(identifier, prepared.deadline)
            reservation = self.change(reservation, ('created',), 'starting')
            self.docker.start(identifier)
            reservation = self.change(reservation, ('starting',), 'running')
            raw = read_frames(stream)

            # A complete output stream does not prove the container has stopped.
            # Check termination within the original analytical deadline.
            while True:
                prepared.deadline.remaining()
                info = self.docker.inspect(identifier)
                if info is None:
                    raise Problem(503, 'dependency_unavailable')
                if not info['State']['Running']:
                    break
                time.sleep(0.02)
            if info['State'].get('OOMKilled'):
                raise Problem(503, 'query_resource_limit')

            # Accept only the runtime's two known error messages on a failed exit.
            # Malformed or unexpected output must not become a public query error.
            body = read_json(raw)
            if info['State']['ExitCode'] != 0:
                code = body.get('error')
                if set(body) == {'error'} and code in ('query_failed', 'query_resource_limit'):
                    raise Problem(422 if code == 'query_failed' else 503, code)
                raise Problem(503, 'dependency_unavailable')

            # Bind successful output to this request, publication and operation
            # before building a response or signing a pagination cursor.
            result = read_result_binding(
                body,
                reservation['request_id'],
                prepared.pinned.publication.version_id,
                prepared.query,
            )
            if isinstance(prepared.query, PreviewOperation):
                response = build_preview_batch_response(
                    prepared.query,
                    prepared.pinned.publication,
                    result,
                    diagnostics=diagnostics,
                    codec=prepared.codec,
                )
            elif isinstance(prepared.query, ChoiceOperation):
                response = build_choice_response(
                    prepared.query,
                    prepared.pinned.publication,
                    result,
                    codec=prepared.codec,
                )
            else:
                data = {
                    **result,
                    'publication': prepared.pinned.publication,
                    'execution_ms': int((time.monotonic() - prepared.started) * 1000),
                }
                response = QueryResponse.model_validate(data)

            # Measure the full serialized response, including metadata and cursors.
            # Exactly 5 MiB is allowed; one byte more fails the response limit.
            if len(response.model_dump_json().encode()) > 5 * 1024 * 1024:
                raise Problem(503, 'query_resource_limit')
            prepared.deadline.remaining()
            outcome = 'succeeded'
        except Problem as error:
            # Cleanup records known query failures. Other failures retain the
            # default dependency outcome without changing the raised Problem.
            if error.code in ('query_failed', 'query_timeout', 'query_resource_limit'):
                outcome = error.code
            raise
        except Exception:
            raise Problem(503, 'dependency_unavailable') from None
        finally:
            # Each nested finally runs even if the preceding close or cleanup
            # fails. Keep the return below this block so failed cleanup cannot
            # send a successful response. Cleanup owns safe capacity release.
            try:
                if attached is not None:
                    attached.close()
            finally:
                try:
                    self.cleanup(reservation, outcome)
                finally:
                    self.close()
        return response

    def recover_one(self):
        """Claim one expired query and prove cleanup; unknown state retains its slot."""
        with self.database.transaction(QueryDeadline(10),error_code='dependency_unavailable') as connection:
            reservation=repository.claim_expired(connection,self.deployment_id)
        if reservation is None:return False
        if reservation['daemon_id']!=self.daemon_id:raise Problem(503,'dependency_unavailable')
        self.cleanup(reservation,'query_timeout')
        return True
