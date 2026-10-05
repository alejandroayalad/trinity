"""Project stored refresh state into bounded Admin tracking responses."""
from trinity.auth.schemas import Action, RefreshSummary
from trinity.errors import Problem
from trinity.refresh.schemas import CandidateRef, FailureWarning, Progress, Run, Step

# Database summaries can contain adapter details. Only stable application codes
# and fixed public text may cross this boundary, including for historical rows.
ERRORS = {
    **{code: 'Publication could not complete.' for code in (
        'storage_temporary','storage_deadline','storage_denied','storage_configuration',
        'evidence_missing','evidence_invalid','unknown_failure','coverage_regression',
        'publication_interrupted','publication_dispatch_exhausted','publication_deadline')},
    'dependency_unavailable': 'A required service is unavailable.',
    'storage_unavailable': 'Candidate storage is unavailable.',
    'publication_unavailable': 'Publication could not complete.',
    'validation_failed': 'Required validation did not pass.',
    'refresh_failed': 'Refresh could not complete.',
    'dispatch_failed': 'Refresh dispatch could not complete.',
    'worker_lost': 'The worker stopped before completing this attempt.',
    'stage_timeout': 'The refresh stage exceeded its time limit.',
}


def safe_error(code):
    """Keep unknown error content private, with a useful generic fallback."""
    if code is None:
        return None, None
    key = code if code in ERRORS else 'refresh_failed'
    return key, ERRORS[key]


def summary(row):
    """Expose just the history identifier, state and times."""
    return RefreshSummary(run_id=row['id'],status=row['status'],
                          requested_at=row['requested_at'],finished_at=row['finished_at'])


def warning_view(row):
    """Retain resolution metadata while excluding raw failure messages."""
    if row is None:
        return None
    code,message = safe_error(row['code'])
    return FailureWarning(warning_id=row['id'],run_id=row['run_id'],version_id=row['version_id'],
        stage=row['stage'],code=code,message=message,created_at=row['created_at'],
        resolved_at=row['resolved_at'],resolution=row['resolution'],resolved_by=row['resolved_by'])


def candidate_view(run, version, approval, publish_step, event):
    """Derive display state; this projection never authorizes publication."""
    if version is None:
        return None
    eligible = version['status']=='validated' and version['diagnostics_frozen_at'] is not None
    approved = bool(approval and approval['manifest_sha256']==version['manifest_sha256']
        and approval['validation_step_id']==version['validation_step_id']
        and approval['review_warning_digest']==version['review_warning_digest'])
    review = ('discarded' if version['disposition']=='discarded' else 'not_ready' if not eligible else
              'not_required' if not version['approval_required'] else 'approved' if approved else 'required')
    publication = 'not_started'
    if event:
        publication = 'published'
    elif version['disposition']!='active' or run['status']=='failed':
        publication = 'blocked'
    elif run['status']=='publication_failed':
        publication = 'failed'
    elif run['status']=='publishing':
        publication = 'publishing' if publish_step and publish_step['status']=='running' else 'queued'
    return CandidateRef(version_id=version['id'],review_status=review,publication_status=publication)


def run_view(detail, steps, cursor, context):
    """Combine fresh run metadata with its pinned page of retained attempts.

    Current admission actions belong to the current lifecycle holder. Never
    show that holder's recovery controls on a different historical run.
    Unknown totals stay null; neither steps nor file counts estimate a percent.
    """
    run,version,warning,approval,publish_step,event = detail
    if run['policy_snapshot'].get('workflow_policy')!='warnings-v1':
        raise Problem(503,'dependency_unavailable')
    owns_slot = context.active_run is not None and context.active_run.run_id==run['id']
    actions = [action if owns_slot or action.action=='start_refresh' else
               Action(action=action.action,enabled=False,reason_code='not_applicable') for action in context.actions]
    items = []
    for row in steps:
        code,message = safe_error(row['error_code'])
        items.append(Step(step_id=row['id'],step_seq=str(row['step_seq']),stage=row['stage'],
            work_key=row['work_key'],attempt=row['attempt'],status=row['status'],started_at=row['started_at'],
            finished_at=row['finished_at'],progress=Progress(processed_count=str(row['processed_count']),
            total_count=str(row['total_count']) if row['total_count'] is not None else None,
            unit=row['progress_unit']),error_code=code,error_summary=message))
    return Run(run_id=run['id'],run_seq=str(run['run_seq']),revision=str(run['revision']),
        trigger_kind=run['trigger_kind'],requested_by=run['requested_by'],rerun_of_run_id=run['rerun_of_run_id'],
        requested_at=run['requested_at'],started_at=run['started_at'],finished_at=run['finished_at'],
        status=run['status'],settings_revision=str(run['settings_revision']),workflow_policy='warnings-v1',
        requested_start=run['requested_start'],requested_end=run['requested_end'],
        candidate=candidate_view(run,version,approval,publish_step,event),warning=warning_view(warning),
        actions=actions,steps=items,next_steps_cursor=cursor,
        poll_after_seconds=2 if run['status'] in ('requested','running','publishing') else None)
