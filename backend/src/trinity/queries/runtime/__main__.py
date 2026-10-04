"""Run one network-disabled, mounted query request and emit one closed result."""
import json
from pathlib import Path
import sys
from uuid import UUID

from trinity.contracts.queries import ValidatedQuery
from trinity.queries.runtime.engine import execute_local, QueryExecutionError


def main():
    """Use fixed mount paths; never initialize auth, PostgreSQL or storage clients."""
    try:
        with Path('/query/request.json').open('rb') as source:
            raw=source.read(256*1024+1)
        if len(raw)>256*1024:raise ValueError
        request=json.loads(raw)
        if (set(request)!={'request_id','version_id','policy','policy_digest'}
                or raw!=json.dumps(request,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()):
            raise ValueError
        for key in ('request_id','version_id'):
            if str(UUID(request[key]))!=request[key]:raise ValueError
        policy=ValidatedQuery.from_bytes(json.dumps(request['policy'],ensure_ascii=True,sort_keys=True,separators=(',',':')).encode())
        if policy.digest!=request['policy_digest']:raise ValueError
        result=execute_local(policy,Path('/query/data'))
        response={k:request[k] for k in ('request_id','version_id','policy_digest')}
        response['result']=result
        output=json.dumps(response,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()
        if len(output)>6*1024*1024:raise QueryExecutionError('query_resource_limit')
        sys.stdout.buffer.write(output)
        return 0
    except QueryExecutionError as error:
        sys.stdout.write(json.dumps({'error':error.code}))
        return 1
    except Exception:
        sys.stdout.write('{"error":"query_failed"}')
        return 1


if __name__=='__main__':raise SystemExit(main())
