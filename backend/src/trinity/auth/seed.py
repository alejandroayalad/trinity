"""Provision missing local personas without changing existing identities.

Passwords come from hidden terminal input or an in-memory test callback.
A mismatch or write failure rolls back the entire batch; secrets are not printed.
"""
from getpass import getpass
import sys
from uuid import uuid4

from trinity.adapters.postgres import Database, Deadline
from trinity.auth.passwords import hash_password
from trinity.auth.repository import find_user
from trinity.config import load_api_settings

PERSONAS = ("viewer", "analyst", "admin")


class SeedError(ValueError):
    """Report only a safe provisioning problem."""


def seed_personas(database, password_source):
    """Atomically create missing personas and preserve all existing records."""
    created = []
    # Prompt/hash outside the transaction so operator typing holds no DB lock.
    with database.transaction(Deadline(), readonly=True) as connection:
        observed = {name: find_user(connection, name) for name in PERSONAS}
    for name, row in observed.items():
        if row and (row["role"] != name or not row["is_active"]):
            raise SeedError("An existing persona has an unexpected role or inactive status.")
    hashes = {}
    for name, row in observed.items():
        if row is None:
            password = password_source(name)
            if not isinstance(password, str) or not 15 <= len(password) <= 1024:
                raise SeedError("Use a password of 15 to 1024 characters.")
            hashes[name] = hash_password(password)
    with database.transaction(Deadline()) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(7083141020)")
        for name in PERSONAS:
            current = find_user(connection, name)
            if current:
                if current["role"] != name or not current["is_active"]:
                    raise SeedError("An existing persona has an unexpected role or inactive status.")
                continue
            if name not in hashes:
                raise SeedError("Persona state changed; rerun provisioning.")
            connection.execute("""INSERT INTO local_users(id,username,password_hash,role)
                VALUES (%s,%s,%s,%s)""", ("local_" + str(uuid4()), name, hashes[name], name))
            created.append(name)
    return created


def main() -> int:
    """Prompt locally and report only created persona names or a safe failure."""
    if not sys.stdin.isatty():
        print("Seed requires a terminal for hidden password input.", file=sys.stderr)
        return 2
    database = None
    try:
        database = Database(load_api_settings())
        database.open()
        created = seed_personas(database, lambda name: getpass(f"Password for {name}: "))
        print("Created: " + (", ".join(created) if created else "none; existing personas preserved"))
        return 0
    except (KeyboardInterrupt, EOFError):
        print("Provisioning cancelled.", file=sys.stderr)
        return 130
    except Exception:
        print("Provisioning failed; check configuration, schema and existing persona status.", file=sys.stderr)
        return 1
    finally:
        if database:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
