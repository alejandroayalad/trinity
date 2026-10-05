"""Dispatch one versioned operation on fixed, network-disabled mount paths."""
import json
from pathlib import Path
import sys

from trinity.contracts.queries import BINDING_FIELDS, MAX_REQUEST_BYTES, read_request
from trinity.queries.runtime.engine import execute_local, QueryExecutionError
from trinity.queries.runtime.preview import execute_preview
from trinity.queries.runtime.choices import execute_choices


def run_request(raw, directory):
    """Validate kind/digest before execution and echo the exact request binding."""
    request, operation = read_request(raw)
    execute = {'preview': execute_preview, 'choices': execute_choices, 'sql': execute_local}[request['operation_kind']]
    result = execute(operation, directory)
    return {**{key: request[key] for key in BINDING_FIELDS}, 'result': result}


def main():
    """Emit one bounded result or a fixed error; never accept client file paths."""
    try:
        with Path('/query/request.json').open('rb') as source:
            raw = source.read(MAX_REQUEST_BYTES + 1)
        response = run_request(raw, Path('/query/data'))
        output = json.dumps(response, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()
        if len(output) > 6 * 1024 * 1024:
            raise QueryExecutionError('query_resource_limit')
        sys.stdout.buffer.write(output)
        return 0
    except QueryExecutionError as error:
        sys.stdout.write(json.dumps({'error': error.code}))
        return 1
    except Exception:
        sys.stdout.write('{"error":"query_failed"}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
