"""Measure verified evidence reads using the operator's existing API environment.

Read the active publication in a read-only database transaction. Measure three
fresh evidence reads through the production verifier. Profile the last read to
separate Python work from I/O; its overhead makes it a different timing sample.
Print only timings, decoded byte counts, safe artifact names and function statistics.
Byte counts describe verified original files, not compressed network traffic.

This is an operator probe, not a product endpoint or a dashboard benchmark. It
does not create sessions, reserve query slots, launch containers or change data.
Run it through docker-entrypoint.sh so the configured database secret is loaded.
Provider failures produce only safe error codes or exception class names.

Use --compare for uncached, cold-cache, warm-cache and concurrent-cold samples.
Use --container NAME from the host to load the reviewed working-tree
modules into an isolated interpreter in that existing container. This changes
no files, installed packages, API process or service configuration. It permits
component comparison before the operator rebuilds the API image.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import cProfile
import hashlib
import io
import json
from pathlib import Path
import pstats
import subprocess
import sys
import threading
import time


def in_container(container, *, compare):
    """Execute selected local code in one disposable interpreter, without installing it.

    Read source files from this repository only. Send them through standard
    input, not command arguments or a retained container file. Credentials stay
    inside the container's existing entrypoint and environment.
    """
    root = Path(__file__).resolve().parents[1]
    names = ('trinity.adapters.s3', 'trinity.queries.staging',
             'trinity.publication.diagnostics', 'trinity.publication.evidence_cache',
             'trinity.queries.client', 'trinity.queries.config')
    sources = [(name, (root / 'backend' / 'src' / (name.replace('.', '/') + '.py')).read_text())
               for name in names]
    # Modules are installed only in this interpreter's import table. Keep parent
    # package attributes consistent with normal Python imports.
    bootstrap = f'''import importlib, sys, types
for name, source in {sources!r}:
    parent_name, _, child = name.rpartition('.')
    parent = importlib.import_module(parent_name)
    module = types.ModuleType(name)
    module.__package__ = parent_name
    sys.modules[name] = module
    setattr(parent, child, module)
    exec(compile(source, '<working-tree:' + name + '>', 'exec'), module.__dict__)
exec(compile({Path(__file__).read_text()!r}, '<evidence-probe>', 'exec'), {{'__name__': '__main__'}})
'''
    command = ['docker', 'exec', '-i', container, 'docker-entrypoint.sh', '/opt/venv/bin/python', '-']
    if compare:
        command.append('--compare')
    return subprocess.run(command, input=bootstrap, text=True, check=False).returncode


def measure_evidence(pinned, execution, *, profiled=False, cache=None, dataset='national'):
    """Time one dataset projection and the verified reads inside it.

    Wrap the reader only for this call. Restore it on every exit. The verifier
    still applies its ordinary hashes, bounds, binding and 30-second deadline.
    """
    from trinity.publication.diagnostics import read_preview_diagnostics
    from trinity.queries.service import QueryDeadline

    reads = []
    original = execution.reader.read_into

    def measured(version, path, output, **kwargs):
        before = time.perf_counter()
        size = original(version, path, output, **kwargs)
        # Label only the three known artifact kinds. Never print an arbitrary
        # storage path supplied by an adapter or a future implementation.
        name = path.rsplit('/', 1)[-1]
        kind = name if name in {'bundle.json', 'validation.json', 'diagnostics.json'} else 'other'
        reads.append({'kind': kind, 'bytes': size, 'byte_basis': 'decoded',
                      'ms': round((time.perf_counter() - before) * 1000, 2)})
        return size

    execution.reader.read_into = measured
    profiler = cProfile.Profile()
    start = time.perf_counter()
    try:
        if profiled:
            profiler.enable()
        if cache is None:
            result = read_preview_diagnostics(pinned, dataset, execution.reader, QueryDeadline(30))
        else:
            result = cache.read(pinned, dataset, execution.reader, QueryDeadline(30),
                                namespace=execution.evidence_namespace)
    finally:
        profiler.disable()
        execution.reader.read_into = original
    elapsed_ms = (time.perf_counter() - start) * 1000
    stats_text = None
    if profiled:
        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats('cumulative')
        stats.print_stats(18)
        stats_text = stream.getvalue()
    if any(note.scope != dataset for note in result):
        raise RuntimeError('Unexpected evidence scope')
    # Compare outputs without printing even the safe note bodies. Computing this
    # fingerprint is outside the measured stage and has no cache side effect.
    signature = hashlib.sha256(json.dumps([note.model_dump() for note in result], sort_keys=True).encode()).hexdigest()
    return {'profiled': profiled, 'evidence_ms': round(elapsed_ms, 2),
            'reads': reads, 'notes': len(result)}, stats_text, signature


def compare_cache(database, pinned):
    """Compare identical verified notes, then count GETs for four cold callers."""
    from trinity.publication.evidence_cache import EvidenceCache
    from trinity.queries.config import execution_factory

    cache = EvidenceCache()
    expected = None
    baseline = None
    for mode, current in (('uncached', None), ('cache_cold', cache), ('cache_warm', cache), ('cache_warm', cache)):
        start = time.perf_counter()
        execution = execution_factory(database)
        factory_ms = (time.perf_counter() - start) * 1000
        try:
            result, _, signature = measure_evidence(pinned, execution, cache=current)
        finally:
            execution.close()
        if expected is None:
            expected, baseline = signature, result
        if signature != expected:
            raise RuntimeError('Cache changed the verified output')
        print(json.dumps({'mode': mode, 'factory_ms': round(factory_ms, 2),
                          'output_matches': True, **result}), flush=True)

    concurrent_cache = EvidenceCache()
    barrier = threading.Barrier(4)

    def read_one(dataset):
        execution = execution_factory(database)
        try:
            # Start the measured stage together after separate reader creation.
            # Distinct dataset projections must still share the evidence fill.
            barrier.wait(timeout=10)
            result, _, _ = measure_evidence(pinned, execution, cache=concurrent_cache, dataset=dataset)
            return {'dataset': dataset, **result}
        finally:
            execution.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read_one, ('national', 'facility', 'generator', 'national')))
    calls = sum(len(result['reads']) for result in results)
    size = sum(read['bytes'] for result in results for read in result['reads'])
    if calls != len(baseline['reads']) or size != sum(read['bytes'] for read in baseline['reads']):
        raise RuntimeError('Concurrent verification was not shared')
    print(json.dumps({'mode': 'concurrent_cold', 'callers': 4, 'evidence_gets': calls,
                      'evidence_bytes': size, 'samples': results}), flush=True)


def main(*, compare=False):
    """Pin once, measure fresh readers, and close every trusted transport."""
    from trinity.adapters.postgres import Database
    from trinity.config import load_api_settings
    from trinity.publication.repository import read_pinned_publication, read_preview_publication
    from trinity.queries.config import execution_factory
    from trinity.queries.service import QueryDeadline

    database = Database(load_api_settings())
    database.open()
    try:
        start = time.perf_counter()
        with database.transaction(QueryDeadline(15), readonly=True) as connection:
            pinned = read_pinned_publication(connection)
            if pinned is None:
                print(json.dumps({'status': 'no_publication'}))
                return 1
            pinned = read_preview_publication(connection, pinned)
        metadata_ms = (time.perf_counter() - start) * 1000

        if compare:
            print(json.dumps({'metadata_ms': round(metadata_ms, 2)}), flush=True)
            compare_cache(database, pinned)
            return 0

        # Separate readers match production's per-request transport creation.
        # These calls read published evidence only; they execute no analytics.
        for sample in range(3):
            start = time.perf_counter()
            execution = execution_factory(database)
            factory_ms = (time.perf_counter() - start) * 1000
            try:
                result, stats_text, _ = measure_evidence(pinned, execution, profiled=sample == 2)
                print(json.dumps({'sample': sample + 1, 'metadata_ms': round(metadata_ms, 2),
                                  'factory_ms': round(factory_ms, 2), **result}), flush=True)
                if stats_text is not None:
                    print(stats_text, flush=True)
            finally:
                execution.close()
    finally:
        database.close()
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', help='Use this existing API container with working-tree modules in an isolated interpreter')
    parser.add_argument('--compare', action='store_true', help='Compare uncached, cold, warm and four concurrent cold reads')
    args = parser.parse_args()
    if args.container:
        raise SystemExit(in_container(args.container, compare=args.compare))
    from trinity.errors import Problem
    try:
        raise SystemExit(main(compare=args.compare))
    except Problem as error:
        print(json.dumps({'status': error.status, 'code': error.code}))
        raise SystemExit(1) from None
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__}))
        raise SystemExit(1) from None
