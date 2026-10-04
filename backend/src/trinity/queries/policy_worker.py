"""Parse bounded SQL with no inherited application credentials or handles."""

import sys
from trinity.queries.runtime.sql_policy import validate_query


def main():
    """Write one closed message; suppress input and parser errors on failure."""
    try:
        data = sys.stdin.buffer.read(16385)
        if not 1 <= len(data) <= 16384:
            return 1
        result = validate_query(data.decode("utf-8"))
        sys.stdout.buffer.write(result.to_bytes())
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
