"""Check three local personas over HTTP without printing credentials or tokens."""

import argparse
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


def check_persona(client, username, password, *, catalog=False, preview=None):
    """Verify auth and optional catalog/preview behavior; attempt logout on failure."""
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
    args = parser.parse_args()
    try:
        preview = load_preview_fixture(args.preview_fixture) if args.preview_fixture is not None else None
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
                                        catalog=args.catalog, preview=preview)
                checks = "login, identity, settings permission, catalog and logout" if args.catalog else (
                    "login, identity, settings permission and logout")
                if preview is not None:
                    checks += ", preview pages, filters and revocation"
                print(f"{username}: {checks} passed; landing={landing}")
        return 0
    except (KeyboardInterrupt, EOFError):
        print("Check cancelled.", file=sys.stderr)
        return 130
    except PreviewNotReady:
        print("Preview check not ready/incomplete; verify publication, fixture and runtime setup.", file=sys.stderr)
        return 2
    except Exception:
        print("Persona check failed; verify local setup and credentials. No secret output retained.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
