"""Rotate the passwords of existing local personas, and change nothing else.

The seed command never changes an existing persona. Use this command when
an operator no longer knows a persona password. The operator names the
personas and types each new password twice through hidden terminal input.

Flow:

1. Read the named personas in a read-only transaction. Each one must exist,
   be active and have the role that matches its name.
2. Ask for the passwords and compute the scrypt hashes outside any
   transaction, so slow typing and hashing hold no database lock.
3. In one write transaction, take the seed advisory lock, lock each user
   row and check that its ID, role and active status did not change since
   step 1. Update only `password_hash`, for exactly one row per persona.

Any failure rolls back the whole batch. The command does not revoke
sessions, reset login limits or touch settings, runs or publication state.
An unexpired session stays valid until it expires. It prints only the
rotated persona names and never prints a password or a hash.
"""
import argparse
from getpass import getpass
import sys

from trinity.adapters.postgres import Database, Deadline
from trinity.auth.passwords import hash_password
from trinity.auth.repository import find_user
from trinity.auth.seed import PERSONAS
from trinity.config import load_api_settings

# The seed command uses the same lock. Rotation and seeding therefore never
# run their write transactions at the same time.
SEED_LOCK = 7083141020


class RotationError(ValueError):
    """Report one fixed, secret-free reason for a refused rotation."""


def _check_persona(row, name):
    """Accept only an existing, active persona whose role matches its name."""
    if row is None:
        raise RotationError("A named persona does not exist; use the seed command to create it.")
    if row["role"] != name or not row["is_active"]:
        raise RotationError("A named persona has an unexpected role or inactive status.")


def rotate_passwords(database, names, password_source):
    """Replace the password hash of each named persona in one transaction.

    names: persona names from PERSONAS, for example ("viewer", "admin").
    password_source: called once per name; returns the new password. It may
    raise RotationError, for example when the two entries differ.

    Return the rotated names in PERSONAS order. Raise RotationError for a
    refused request; nothing is written in that case.
    """
    if not names or len(set(names)) != len(names) or not set(names) <= set(PERSONAS):
        raise RotationError("Name one or more of viewer, analyst and admin, each once.")
    ordered = [name for name in PERSONAS if name in names]

    # Step 1: observe the personas without locks.
    with database.transaction(Deadline(), readonly=True) as connection:
        observed = {name: find_user(connection, name) for name in ordered}
    for name in ordered:
        _check_persona(observed[name], name)

    # Step 2: prompt and hash outside any transaction. The length rule is the
    # seed rule: "a" * 15 is accepted, "a" * 14 is rejected.
    hashes = {}
    for name in ordered:
        password = password_source(name)
        if not isinstance(password, str) or not 15 <= len(password) <= 1024:
            raise RotationError("Use a password of 15 to 1024 characters.")
        hashes[name] = hash_password(password)

    # Step 3: one write transaction for the whole batch.
    with database.transaction(Deadline()) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (SEED_LOCK,))
        for name in ordered:
            current = find_user(connection, name, lock=True)
            _check_persona(current, name)
            # A different ID means that the account was replaced while the
            # operator typed. Refuse instead of changing an unseen account.
            if current["id"] != observed[name]["id"]:
                raise RotationError("Persona state changed; rerun rotation.")
            # The WHERE clause repeats every identity check, so the UPDATE
            # can change only the row that was checked above.
            row = connection.execute("""UPDATE local_users SET password_hash=%s
                WHERE id=%s AND username=%s AND role=%s AND is_active RETURNING id""",
                (hashes[name], current["id"], name, name)).fetchone()
            if row is None:
                raise RotationError("Persona state changed; rerun rotation.")
    return ordered


def _prompt(name):
    """Ask twice with hidden input; refuse when the two entries differ."""
    first = getpass(f"New password for {name}: ")
    second = getpass(f"Repeat new password for {name}: ")
    if first != second:
        raise RotationError("The two password entries differ; nothing was changed.")
    return first


def main(argv=None) -> int:
    """Rotate the named personas and print only their names or a fixed failure."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("personas", nargs="+", choices=PERSONAS, help="Persona names to rotate")
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        print("Rotation requires a terminal for hidden password input.", file=sys.stderr)
        return 2
    database = None
    try:
        database = Database(load_api_settings())
        database.open()
        rotated = rotate_passwords(database, args.personas, _prompt)
        print("Rotated: " + ", ".join(rotated))
        return 0
    except (KeyboardInterrupt, EOFError):
        print("Rotation cancelled.", file=sys.stderr)
        return 130
    except RotationError as error:
        # These messages are fixed strings without input values.
        print(f"Rotation refused: {error}", file=sys.stderr)
        return 1
    except Exception:
        # A lost connection during COMMIT leaves the outcome unknown, so do
        # not claim that nothing changed. Log in to find the current state.
        print("Rotation failed. Check configuration and database access before you retry.", file=sys.stderr)
        return 1
    finally:
        if database:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
