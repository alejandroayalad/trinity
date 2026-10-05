"""Read the Admin candidate panel from one persisted application-state snapshot.

Resolve the current session before parsing the protected target or reading it.
Project measured validation rows and stored review/publication state. Missing
checks stay absent; no storage read, validation run or publication occurs here.
Messages come from fixed application text, never private evidence or SDK errors.
"""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from trinity.adapters.postgres import Deadline
from trinity.auth.dependencies import bearer_token
from trinity.auth.schemas import Action, StrictModel
from trinity.connector.validate import MESSAGES, REQUIRED_CHECKS
from trinity.errors import Problem
from trinity.refresh import repository
from trinity.refresh.router import service
from trinity.refresh.schemas import Counter, FailureWarning
from trinity.refresh.service import _authorize, admin_context
from trinity.refresh.tracking import candidate_view, safe_error, warning_view
from trinity.settings.repository import read_settings

Scope = Literal['national','facility','generator','all']
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class DateRange(StrictModel):
    """Show the frozen requested coverage, including its bounds."""
    start: date
    end: date


class ValidationCheck(StrictModel):
    """Expose one actual required check without its private detail path."""
    code: str = Field(pattern=r'^V[0-9]{2}$')
    scope: Scope
    status: Literal['pass','fail','error']
    checked_count: Counter
    failed_count: Counter
    checked_at: datetime
    message: str = Field(max_length=512)


class Validation(StrictModel):
    """Measure progress against the fixed sixteen-slot required registry."""
    status: Literal['pending','running','passed','failed','incomplete']
    step_id: UUID | None
    checkset: Literal['trinity-data-v1']
    expected_required_count: Literal[16] = 16
    passed_required_count: int = Field(ge=0,le=16)
    checks: list[ValidationCheck] = Field(max_length=16)


class Diagnostic(StrictModel):
    """Show only completed diagnostic evaluations and measured affected counts."""
    code: str = Field(pattern=r'^D[0-9]{2}$')
    severity: Literal['info','warning']
    scope: Scope
    message: str = Field(max_length=512)
    affected_count: Counter


class Approval(StrictModel):
    """Expose the retained approval's exact evidence binding."""
    approval_id: UUID
    approved_by: str = Field(max_length=128)
    approved_at: datetime
    manifest_sha256: Digest
    validation_step_id: UUID
    review_warning_digest: Digest


class PublicationProgress(StrictModel):
    """Keep a queued obligation distinct from an actual publication attempt."""
    status: Literal['not_started','queued','publishing','failed','published','blocked']
    generation: Counter
    attempt: int = Field(ge=0)
    error_code: str | None
    error_summary: str | None
    published_at: datetime | None
    publication_event_id: UUID | None


class Candidate(StrictModel):
    """Return canonical candidate detail without exposing unpublished files."""
    version_id: UUID
    run_id: UUID
    revision: Counter
    validation_status: Literal['preparing','validating','validated','rejected']
    disposition: Literal['active','discarded','superseded']
    created_at: datetime
    coverage: DateRange
    latest_observation_date: date
    manifest_sha256: Digest | None
    validation: Validation
    diagnostics: list[Diagnostic] = Field(max_length=32)
    review_warning_count: Counter | None
    review_warning_digest: Digest | None
    review_status: Literal['not_ready','not_required','required','approved','discarded']
    approval_required: bool | None
    approval: Approval | None
    publication: PublicationProgress
    failure_warning: FailureWarning | None
    discarded_at: datetime | None
    discarded_by: str | None
    actions: list[Action] = Field(max_length=6)


def read_candidate(database, token, version_id, pairs=(), *, body=b''):
    """Authorize first, then read actual evidence and actions in one snapshot."""
    with database.transaction(Deadline(),readonly=True,error_code='dependency_unavailable') as connection:
        _authorize(connection,token,'candidate:review')
        try:
            identifier = UUID(version_id)
            if str(identifier) != version_id.lower() or pairs or body:
                raise ValueError
        except (ValueError,TypeError,AttributeError):
            raise Problem(422,'invalid_request') from None
        version = connection.execute('SELECT * FROM data_versions WHERE id=%s',(identifier,)).fetchone()
        if version is None:
            raise Problem(404,'resource_not_found')
        run,_,warning,approval,publish_step,event = repository.run_detail(connection,version['run_id'])
        state = candidate_view(run,version,approval,publish_step,event)
        # Successful registration selects a step. Before that, use the durable
        # latest attempt, including stopped attempts with only partial results.
        step = connection.execute('''SELECT * FROM refresh_steps WHERE run_id=%s AND stage='validate'
            AND (%s::uuid IS NULL OR id=%s) ORDER BY step_seq DESC LIMIT 1''',
            (run['id'],version['validation_step_id'],version['validation_step_id'])).fetchone()
        rows = connection.execute('''SELECT * FROM validation_results WHERE version_id=%s AND step_id=%s
            ORDER BY check_code,dataset_key''',(identifier,step['id'] if step else None)).fetchall()
        checks = [ValidationCheck(code=row['check_code'],scope=row['dataset_key'],status=row['status'],
            checked_count=str(row['checked_count']),failed_count=str(row['failed_count']),
            checked_at=row['checked_at'],message={'pass':'Required check passed.',
            'fail':'Required check failed.','error':'Required check could not complete.'}[row['status']])
            for row in rows if row['required'] and (row['check_code'],row['dataset_key']) in REQUIRED_CHECKS]
        passed = sum(check.status=='pass' for check in checks)
        validation_status = ('failed' if any(check.status in ('fail','error') for check in checks) else
            'passed' if passed==16 else 'pending' if step is None else
            'running' if step['status']=='running' else 'incomplete')
        # An evaluation error has no reliable affected count. Preserve it in
        # the database, but do not disguise it as a successful diagnostic here.
        diagnostics = [Diagnostic(code=row['check_code'],scope=row['dataset_key'],severity=row['severity'],
            message=MESSAGES[row['check_code']],affected_count=str(row['failed_count'])) for row in rows
            if not row['required'] and row['status']!='error' and row['check_code'] in MESSAGES]
        context = admin_context(read_settings(connection),*repository.read_context(connection))
        owns_slot = context.active_run is not None and context.active_run.run_id==run['id']
        actions = [action if owns_slot or action.action=='start_refresh' else
            Action(action=action.action,enabled=False,reason_code='not_applicable') for action in context.actions]
        publication_step = connection.execute("""SELECT * FROM refresh_steps WHERE run_id=%s
            AND stage='publish' ORDER BY step_seq DESC LIMIT 1""",(run['id'],)).fetchone()
        publication_event = connection.execute('SELECT * FROM publication_events WHERE version_id=%s',
                                                (identifier,)).fetchone()
        code,message = safe_error(publication_step['error_code'] if publication_step else None)
        return Candidate(version_id=identifier,run_id=run['id'],revision=str(version['revision']),
            validation_status=version['status'],disposition=version['disposition'],created_at=version['created_at'],
            coverage=DateRange(start=version['coverage_start'],end=version['coverage_end']),
            latest_observation_date=version['latest_observation_date'],manifest_sha256=version['manifest_sha256'],
            validation=Validation(status=validation_status,step_id=step['id'] if step else None,
                checkset=version['validation_checkset'],passed_required_count=passed,checks=checks),
            diagnostics=diagnostics,review_warning_count=str(version['review_warning_count'])
                if version['review_warning_count'] is not None else None,
            review_warning_digest=version['review_warning_digest'],review_status=state.review_status,
            approval_required=version['approval_required'],approval=Approval(approval_id=approval['id'],
                **{key:approval[key] for key in Approval.model_fields if key!='approval_id'}) if approval else None,
            publication=PublicationProgress(status=state.publication_status,generation=str(run['publication_generation']),
                attempt=publication_step['attempt'] if publication_step else 0,error_code=code,error_summary=message,
                published_at=publication_event['published_at'] if publication_event else None,
                publication_event_id=publication_event['id'] if publication_event else None),
            failure_warning=warning_view(warning),discarded_at=version['discarded_at'],
            discarded_by=version['discarded_by'],actions=actions)


router = APIRouter(prefix='/api/v1/candidates',tags=['refresh'])


@router.get('/{version_id}',response_model=Candidate)
async def detail(version_id: str, request: Request, response: Response):
    """Return a no-store Admin snapshot with its canonical candidate revision."""
    result = await run_in_threadpool(read_candidate,service(request).database,bearer_token(request),
        version_id,request.query_params.multi_items(),body=await request.body())
    response.headers['ETag'] = f'"candidate-{result.revision}"'
    return result
