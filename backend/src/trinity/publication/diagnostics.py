"""Read frozen candidate evidence through the active publication's trusted index."""

import io
import re

from trinity.connector.validate import (
    CheckResult, DIAGNOSTIC_CHECKS, DIAGNOSTIC_REGISTRY, REQUIRED_CHECKS,
    diagnostic_identity, required_checks_pass,
)
from trinity.contracts.datasets import DATASETS
from trinity.contracts.manifest import canonical_json, read_json, safe_relative_path, sha256
from trinity.errors import Problem
from trinity.queries.preview_schemas import PreviewDiagnostic

# Each uncached verification reads validation.json and diagnostics.json. They embed
# every check's detail bytes. A full live window (2024-10-02 to 2026-10-05) made
# validation.json 14.9 MB, mostly V06 detail, so the earlier 4 MiB limit failed
# every Preview. Alayala selected 64 MiB. A larger file still fails closed.
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024


def read_preview_diagnostics(pinned, dataset, reader, deadline):
    """Verify bundle/member hashes and complete evaluations before projecting notes.

    Read only the bundle and two summaries from the pinned version. Required and
    diagnostic detail bytes are already embedded in these summaries. Verify their
    identities against the bundle without loading another analytical dataset.
    Missing or partial evidence fails closed, including when no warning is listed.
    """
    try:
        if dataset not in DATASETS:
            raise ValueError
        version = str(pinned.publication.version_id)

        def fetch(path, digest, size=None):
            output = io.BytesIO()
            reader.read_into(version, path, output, deadline=deadline, max_bytes=MAX_EVIDENCE_BYTES,
                             digest=digest, expected_size=size)
            raw = output.getvalue()
            body = read_json(raw)
            if canonical_json(body) != raw:
                raise ValueError
            return body

        bundle = fetch('bundle.json', pinned.evidence_bundle_sha256)
        binding = dict(version_id=version, attempt_id=pinned.validation_attempt_id,
                       manifest_sha256=pinned.manifest_sha256, checkset_version=pinned.validation_checkset,
                       contract_version=1, requested_start=pinned.publication.coverage_start.isoformat(),
                       requested_end=pinned.publication.coverage_end.isoformat())
        warning = dict(warning_digest=pinned.review_warning_digest, warning_count=pinned.review_warning_count,
                       approval_required=pinned.approval_required)
        if (set(bundle) != {*binding, *warning, 'bundle_format', 'published', 'artifacts'}
                or type(bundle['bundle_format']) is not int or bundle['bundle_format'] != 1
                or type(bundle['contract_version']) is not int
                or bundle['published'] is not False
                or any(bundle[key] != value for key, value in (binding | warning).items())
                or type(bundle['warning_count']) is not int or type(bundle['approval_required']) is not bool
                or type(bundle['artifacts']) is not list or not 1 <= len(bundle['artifacts']) <= 8192):
            raise ValueError
        artifacts = {}
        for item in bundle['artifacts']:
            if set(item) != {'storage_path', 'byte_size', 'sha256'}:
                raise ValueError
            path = item['storage_path']
            safe_relative_path(path)
            if (path in artifacts or type(item['byte_size']) is not int or item['byte_size'] < 0
                    or re.fullmatch(r'[0-9a-f]{64}', item['sha256']) is None):
                raise ValueError
            artifacts[path] = item
        if artifacts['manifest.json']['sha256'] != pinned.manifest_sha256:
            raise ValueError

        prefix = f'evidence/{pinned.validation_attempt_id}'

        def summary(name, fields):
            member = artifacts[f'{prefix}/{name}.json']
            body = fetch(member['storage_path'], member['sha256'], member['byte_size'])
            if (set(body) != {*binding, *fields} or type(body['contract_version']) is not int
                    or any(body[key] != value for key, value in binding.items())):
                raise ValueError
            return body

        validation = summary('validation', ('status', 'expected_checks', 'results', 'error_code'))
        diagnostics = summary('diagnostics', ('registry', 'frozen', *warning, 'summaries', 'evaluations'))

        def checks(items, expected):
            if type(items) is not list or len(items) != len(expected):
                raise ValueError
            results = []
            for item in items:
                fields = set(CheckResult.__dataclass_fields__) - {'details_json'}
                if set(item) != fields | {'details', 'details_sha256'}:
                    raise ValueError
                details = canonical_json(item['details'])
                path = f"{prefix}/{item['check_code']}-{item['dataset_key']}.json"
                if (item['details_path'] != path or sha256(details) != item['details_sha256']
                        or artifacts[path]['sha256'] != item['details_sha256']
                        or artifacts[path]['byte_size'] != len(details)
                        or any(item[key] != binding[key] for key in
                               ('version_id', 'attempt_id', 'manifest_sha256', 'checkset_version'))):
                    raise ValueError
                results.append(CheckResult(**{key: item[key] for key in fields}, details_json=details))
            return results

        required = checks(validation['results'], REQUIRED_CHECKS)
        evaluated = checks(diagnostics['evaluations'], DIAGNOSTIC_CHECKS)
        if (validation['status'] != 'passed' or validation['error_code'] is not None
                or validation['expected_checks'] != [list(item) for item in REQUIRED_CHECKS]
                or not required_checks_pass(required, version_id=version, attempt_id=pinned.validation_attempt_id,
                                            manifest_sha256=pinned.manifest_sha256)
                or diagnostics['frozen'] is not True or diagnostics['registry'] != DIAGNOSTIC_REGISTRY
                or type(diagnostics['warning_count']) is not int
                or type(diagnostics['approval_required']) is not bool
                or any(diagnostics[key] != value for key, value in warning.items())):
            raise ValueError
        digest, count, summaries = diagnostic_identity(evaluated)
        if (digest != pinned.review_warning_digest or count != pinned.review_warning_count
                or diagnostics['summaries'] != summaries):
            raise ValueError
        # Counts describe the frozen dataset, not the current page. D09 is never
        # a preview note, even for Admin; raw diagnostic details stay trusted.
        result = [PreviewDiagnostic(code=item['code'], severity=item['severity'], scope=dataset,
                                    message=item['message'], affected_count=str(item['affected_count']))
                  for item in summaries if item['dataset_key'] == dataset and item['code'] != 'D09'
                  and item['affected_count'] > 0]
        if len(result) > 32:
            raise ValueError
        deadline.remaining()
        return result
    except Problem:
        raise
    except Exception:
        raise Problem(503, 'dependency_unavailable') from None
