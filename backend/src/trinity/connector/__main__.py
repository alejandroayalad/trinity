"""Run all three EIA routes and save one JSONL evidence record per route."""

import argparse
import asyncio
from datetime import date
import json
import os
from pathlib import Path
import sys

from trinity.connector.pipeline import retrieve_all
from trinity.connector.retrieval import RetrievalResult


def main(argv: list[str] | None = None) -> int:
    """Extract a date window and save route evidence to a new JSONL file.

    Use process arguments when argv is None. Sync each route before the next one.
    Return 0 on success, 1 on route failure, 2 on file failure, or 130 on cancellation.
    Invalid command syntax exits through argparse before retrieval starts.
    Evidence for an unfinished route can be lost if the process is killed.
    The output holds sanitized retrieval evidence, not normalized or published data.
    """
    # argparse converts date and path text before retrieval. Bad syntax exits here.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="New JSONL evidence file; existing files are never overwritten.")
    parser.add_argument("--page-size", type=int, default=5000)
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--timeout-seconds", type=float, default=300.0,
                        help="Total deadline per route, including retries.")
    args = parser.parse_args(argv)

    try:
        # Refuse an existing path before making requests, so prior evidence stays intact.
        with args.output.open("x", encoding="utf-8") as output:
            def save(result: RetrievalResult) -> None:
                """Persist full route evidence and print a summary without attempt bodies."""
                # JSONL stores one route per line. flush moves Python's buffer to
                # the OS; fsync requests disk persistence before the next route starts.
                output.write(json.dumps(result.metadata.to_dict(), ensure_ascii=True) + "\n")
                output.flush()
                os.fsync(output.fileno())
                print(json.dumps(result.metadata.to_dict(include_attempts=False)))

            # Run the async connector from this synchronous command. The callback
            # writes each result as it arrives instead of waiting for all routes.
            results = asyncio.run(retrieve_all(
                start=args.start, end=args.end, page_size=args.page_size,
                max_pages=args.max_pages, timeout_seconds=args.timeout_seconds,
                on_result=save,
            ))
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Keep already written evidence and use the conventional interrupt exit code.
        print("Extraction cancelled. Completed route evidence was retained.", file=sys.stderr)
        return 130
    except OSError:
        # File errors can contain private paths or details; print only safe guidance.
        print("Cannot create or write retrieval output; use a new file in a writable directory.",
              file=sys.stderr)
        return 2
    return 0 if all(r.metadata.final_status == "success" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
