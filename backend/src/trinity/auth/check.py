"""Check three local personas over HTTP without printing credentials or tokens."""

import argparse
from getpass import getpass
import sys
from urllib.parse import urlsplit

import httpx


def check_persona(client, username, password):
    """Verify login, app entry, settings access and revocation for one persona."""
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
    finally:
        logout = client.post("/api/v1/auth/logout", json={}, headers=headers)
    if logout.status_code != 204 or logout.content:
        raise ValueError("Logout check failed")
    if client.get("/api/v1/me", headers=headers).status_code != 401:
        raise ValueError("Revocation check failed")
    return me.json()["landing_screen"]


def main() -> int:
    """Prompt in the terminal and print only safe pass/fail summaries."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        url = urlsplit(args.base_url)
        if (url.username or url.password or url.query or url.fragment or url.path not in ("", "/")
                or url.scheme not in ("http", "https") or not url.hostname
                or (url.scheme == "http" and url.hostname not in ("127.0.0.1", "localhost", "::1"))):
            raise ValueError
        if not sys.stdin.isatty():
            raise ValueError
        with httpx.Client(base_url=args.base_url, timeout=20, follow_redirects=False, trust_env=False) as client:
            for username in ("viewer", "analyst", "admin"):
                landing = check_persona(client, username, getpass(f"Password for {username}: "))
                print(f"{username}: login, identity, settings permission and logout passed; landing={landing}")
        return 0
    except (KeyboardInterrupt, EOFError):
        print("Check cancelled.", file=sys.stderr)
        return 130
    except Exception:
        print("Persona check failed; verify local setup and credentials. No secret output retained.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
