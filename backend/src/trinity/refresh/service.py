"""Derive app-entry actions from retained lifecycle evidence."""
from trinity.auth.schemas import Action, AdminContext, Blocker, RefreshSummary


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
    eligible = bool(version and version["status"] == "validated" and version["disposition"] == "active"
                    and version["diagnostics_frozen_at"] and step and step["status"] == "succeeded"
                    and step["stage"] == "validate" and step["run_id"] == run["id"])
    approved = bool(eligible and (not version["approval_required"] or
                    (approval and approval["manifest_sha256"] == version["manifest_sha256"]
                     and approval["validation_step_id"] == version["validation_step_id"]
                     and approval["review_warning_digest"] == version["review_warning_digest"])))
    # Publication retry is enabled only for known recoverable operational failures.
    recoverable = bool(warning and warning["code"] in
                       ("dependency_unavailable", "storage_unavailable", "publication_unavailable"))
    enabled = {
        "start_refresh": setup and run is None,
        "rerun": setup and status in ("failed", "publication_failed") and bool(warning),
        "delete_warning": setup and status in ("failed", "publication_failed") and bool(warning),
        "approve": setup and status == "awaiting_approval" and eligible and bool(version["approval_required"]),
        "publication_retry": setup and status == "publication_failed" and approved and recoverable,
        "discard": setup and status in ("awaiting_approval", "publication_failed")
                   and bool(version and version["disposition"] == "active"),
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
