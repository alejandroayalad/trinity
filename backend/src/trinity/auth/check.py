"""Check three local personas over HTTP without printing credentials or tokens.

With --schedule HH:MM TIMEZONE, the Admin also saves an enabled daily
schedule, reads the schedule status and confirms that the refresh run
history did not change. Viewer and Analyst must be denied. This writes the
shared settings row; the first save completes setup and cannot be undone
through the API.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
import sys
from urllib.parse import urlsplit

import httpx

from trinity.catalog.schemas import CatalogResponse
from trinity.auth.preview_check import PreviewNotReady, check_preview, load_preview_fixture


def check_catalog(response, role):
    """Validate permitted catalog metadata without printing its response."""
    if response.status_code != 200 or response.headers.get("cache-control") != "no-store":
        raise ValueError("Catalog check failed")
    catalog = CatalogResponse.model_validate_json(response.content)
    expected = ["national_outages"] if role == "viewer" else [
        "national_outages", "facility_outages", "generator_outages",
    ]
    if [dataset.key for dataset in catalog.datasets] != expected:
        raise ValueError("Catalog permission check failed")


class CheckFailed(ValueError):
    """Carry one fixed, secret-free message that main() may print."""


@dataclass
class ScheduleCheck:
    """Hold the operator's schedule input and, after the check, a safe summary.

    daily_time and timezone are the values to save, for example "06:15" and
    "America/New_York". The schedule is always saved as enabled, so the
    status shows a next check. check_schedule sets summary for the Admin.
    """
    daily_time: str
    timezone: str
    summary: str | None = None


def _run_count(client, headers):
    """Return the first-page run count and the active run ID from run history."""
    history = client.get("/api/v1/refresh-runs", headers=headers)
    if history.status_code != 200:
        raise CheckFailed("Refresh history check failed")
    data = history.json()
    return len(data["items"]), (data["active_run"] or {}).get("run_id")


def check_schedule(client, headers, role, schedule):
    """Save one enabled schedule as Admin and prove that no run started.

    Viewer and Analyst must receive 403 for the save and the status, and
    nothing is saved. For the Admin:

    1. Read the settings and their ETag, and the run history.
    2. Save the schedule with that ETag. Identical values are a no-op save
       and keep the revision; changed values give the next revision.
    3. After a revision change, repeat the old ETag: it must get 412.
    4. Read the status: same revision, a next check after evaluated_at.
    5. Read the run history again: same run count and active run.

    Raise CheckFailed with a fixed message on any difference. The saved
    values stay in place after a failure in steps 3–5; the summary lists
    only revisions, the next check time, the blocker code and the count.
    """
    body = {"schedule_enabled": True, "daily_time": schedule.daily_time, "timezone": schedule.timezone}
    if role != "admin":
        denied_save = client.put("/api/v1/settings", json=body, headers={**headers, "If-Match": '"settings-0"'})
        denied_status = client.get("/api/v1/settings/schedule-status", headers=headers)
        if (denied_save.status_code, denied_status.status_code) != (403, 403):
            raise CheckFailed("Schedule permission check failed")
        return
    before = client.get("/api/v1/settings", headers=headers)
    if before.status_code != 200 or not before.headers.get("etag"):
        raise CheckFailed("Settings read check failed")
    runs_before = _run_count(client, headers)
    saved = client.put("/api/v1/settings", json=body, headers={**headers, "If-Match": before.headers["etag"]})
    if saved.status_code != 200:
        # A 422 here usually means a timezone name that the server rejects.
        raise CheckFailed(f"Schedule save failed with HTTP {saved.status_code}")
    old, new = int(before.json()["revision"]), int(saved.json()["revision"])
    values = saved.json()
    if (new not in (old, old + 1) or saved.headers.get("etag") != f'"settings-{new}"'
            or values["setup_completed_at"] is None
            or (values["schedule_enabled"], values["daily_time"], values["timezone"]) != tuple(body.values())):
        raise CheckFailed("Schedule save check failed")
    if new != old:
        stale = client.put("/api/v1/settings", json=body, headers={**headers, "If-Match": before.headers["etag"]})
        if stale.status_code != 412:
            raise CheckFailed("Stale revision check failed")
    status = client.get("/api/v1/settings/schedule-status", headers=headers)
    data = status.json() if status.status_code == 200 else {}
    if (status.status_code != 200 or data["settings_revision"] != str(new) or not data["schedule_enabled"]
            or data["next_check_at"] is None
            or datetime.fromisoformat(data["next_check_at"]) <= datetime.fromisoformat(data["evaluated_at"])):
        raise CheckFailed("Schedule status check failed")
    if _run_count(client, headers) != runs_before:
        raise CheckFailed("No-run check failed: run history changed")
    blocker = data["blocker"]["code"] if data["blocker"] else "none"
    schedule.summary = (f"revision {old}->{new}{' (no-op)' if new == old else ''}; "
                        f"next check {data['next_check_local']}; blocker {blocker}; "
                        f"refresh runs unchanged ({runs_before[0]})")


def check_persona(client, username, password, *, catalog=False, preview=None, schedule=None):
    """Verify auth and optional catalog/preview/schedule behavior; attempt logout on failure."""
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    if login.status_code != 200:
        raise ValueError("Login check failed")
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    try:
        me = client.get("/api/v1/me", headers=headers)
        if me.status_code != 200 or me.json()["role"] != username:
            raise ValueError("Identity check failed")
        settings = client.get("/api/v1/settings", headers=headers)
        if settings.status_code != (200 if username == "admin" else 403):
            raise ValueError("Permission check failed")
        if catalog:
            check_catalog(client.get("/api/v1/catalog", headers=headers), username)
        if preview is not None:
            check_preview(client, headers, username, preview)
        if schedule is not None:
            check_schedule(client, headers, username, schedule)
            # The first save completes setup, so the Admin landing screen
            # changes. Read it again so the printed landing is current.
            me = client.get("/api/v1/me", headers=headers)
            if me.status_code != 200:
                raise ValueError("Identity check failed")
    finally:
        logout = client.post("/api/v1/auth/logout", json={}, headers=headers)
    if logout.status_code != 204 or logout.content:
        raise ValueError("Logout check failed")
    if client.get("/api/v1/me", headers=headers).status_code != 401:
        raise ValueError("Revocation check failed")
    if catalog and client.get("/api/v1/catalog", headers=headers).status_code != 401:
        raise ValueError("Catalog revocation check failed")
    if preview is not None and client.get("/api/v1/datasets/national_outages/preview", headers=headers).status_code != 401:
        raise ValueError("Preview revocation check failed")
    return me.json()["landing_screen"]


def main() -> int:
    """Prompt in the terminal and print only safe pass/fail summaries."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--catalog", action="store_true", help="Also verify catalog access and revocation")
    parser.add_argument("--preview-fixture", help="Verify preview against a private, known-publication JSON fixture")
    parser.add_argument("--schedule", nargs=2, metavar=("HH:MM", "TIMEZONE"),
                        help="As Admin, save this enabled daily schedule and confirm no refresh run starts")
    args = parser.parse_args()
    try:
        preview = load_preview_fixture(args.preview_fixture) if args.preview_fixture is not None else None
        schedule = ScheduleCheck(*args.schedule) if args.schedule else None
        url = urlsplit(args.base_url)
        if (url.username or url.password or url.query or url.fragment or url.path not in ("", "/")
                or url.scheme not in ("http", "https") or not url.hostname
                or (url.scheme == "http" and url.hostname not in ("127.0.0.1", "localhost", "::1"))):
            raise ValueError
        if not sys.stdin.isatty():
            raise ValueError
        with httpx.Client(base_url=args.base_url, timeout=40 if preview is not None else 20,
                          follow_redirects=False, trust_env=False) as client:
            for username in ("viewer", "analyst", "admin"):
                landing = check_persona(client, username, getpass(f"Password for {username}: "),
                                        catalog=args.catalog, preview=preview, schedule=schedule)
                checks = "login, identity, settings permission, catalog and logout" if args.catalog else (
                    "login, identity, settings permission and logout")
                if preview is not None:
                    checks += ", preview pages, filters and revocation"
                if schedule is not None:
                    checks += ", schedule save" if username == "admin" else ", schedule denial"
                print(f"{username}: {checks} passed; landing={landing}")
            if schedule is not None:
                print(f"admin schedule: {schedule.summary}")
        return 0
    except (KeyboardInterrupt, EOFError):
        print("Check cancelled.", file=sys.stderr)
        return 130
    except CheckFailed as error:
        # These messages are fixed strings with at most an HTTP status code.
        print(f"Persona check failed: {error}. No secret output retained.", file=sys.stderr)
        return 1
    except PreviewNotReady:
        print("Preview check not ready/incomplete; verify publication, fixture and runtime setup.", file=sys.stderr)
        return 2
    except Exception:
        print("Persona check failed; verify local setup and credentials. No secret output retained.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
