"""Check known published rows over HTTP without retaining tokens or cursor output."""

from pathlib import Path

from pydantic import Field, model_validator

from trinity.auth.schemas import Publication, StrictModel
from trinity.catalog.registry import describe_dataset
from trinity.queries.preview import PUBLIC_DATASETS, source_id
from trinity.queries.preview_schemas import PreviewDiagnostic, PreviewRange, PreviewResponse


class PreviewNotReady(ValueError):
    """Distinguish an incomplete operator prerequisite from a passing check."""


class PreviewFixture(StrictModel):
    """Pin the first two filtered rows and frozen summaries for one publication."""
    publication: Publication
    range: PreviewRange
    facility: str
    generator: str
    rows: dict[str, list[list[str | None]]] = Field(repr=False)
    diagnostics: dict[str, list[PreviewDiagnostic]]

    @model_validator(mode='after')
    def known_rows(self):
        """Reject incomplete, unordered or filter-inconsistent expectations."""
        source_id(self.facility)
        source_id(self.generator)
        if set(self.rows) != set(PUBLIC_DATASETS) or set(self.diagnostics) != set(PUBLIC_DATASETS):
            raise ValueError('All three datasets are required')
        for public, internal in PUBLIC_DATASETS.items():
            rows = self.rows[public]
            if len(rows) != 2:
                raise ValueError('Two expected rows are required')
            # Reuse the public schema to reject invalid cells, keys and diagnostic scopes.
            PreviewResponse(publication=self.publication, dataset_key=public, range=self.range,
                            columns=describe_dataset(internal).columns, rows=rows, returned_rows=2,
                            next_cursor=None, reason=None, diagnostics=self.diagnostics[public])
            if internal != 'national' and any(row[1] != self.facility for row in rows):
                raise ValueError('Facility does not match expected rows')
            if internal == 'generator' and any(row[2] != self.generator for row in rows):
                raise ValueError('Generator does not match expected rows')
        return self


def load_preview_fixture(path):
    """Read a bounded private fixture; missing or incomplete input is not readiness."""
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(131073)
        if len(data) > 131072:
            raise ValueError
        return PreviewFixture.model_validate_json(data)
    except Exception:
        raise PreviewNotReady('Preview fixture is missing or incomplete') from None


def check_preview(client, headers, role, fixture):
    """Verify two exact pages per permitted dataset and Viewer detail denial.

    The fixture must come from independently verified publication evidence.
    This check does not publish data or prove that a fabricated fixture is real.
    The caller owns login/logout. Responses and cursors remain in memory only.
    """
    for public, internal in PUBLIC_DATASETS.items():
        url = f'/api/v1/datasets/{public}/preview'
        params = {'start': fixture.range.start.isoformat(), 'end': fixture.range.end.isoformat(), 'limit': '1'}
        if role == 'viewer' and internal != 'national':
            response = client.get(url, headers=headers, params=params)
            if (response.status_code != 404 or response.json().get('code') != 'dataset_not_found'
                    or response.headers.get('cache-control') != 'no-store'):
                raise ValueError('Preview permission check failed')
            continue
        if internal != 'national':
            params['facility'] = fixture.facility
        if internal == 'generator':
            params['generator'] = fixture.generator
        for index in range(2):
            response = client.get(url, headers=headers, params=params)
            if response.status_code == 503:
                raise PreviewNotReady('Published preview is unavailable')
            if (response.status_code != 200 or response.headers.get('cache-control') != 'no-store'
                    or not response.headers.get('x-request-id')):
                raise ValueError('Preview HTTP check failed')
            page = PreviewResponse.model_validate_json(response.content)
            if not page.rows:
                raise PreviewNotReady('Preview has insufficient matching rows')
            if (page.publication != fixture.publication or page.dataset_key != public
                    or page.range != fixture.range or page.rows != [fixture.rows[public][index]]
                    or page.diagnostics != fixture.diagnostics[public]):
                raise ValueError('Preview evidence check failed')
            if index == 0:
                if page.next_cursor is None:
                    raise PreviewNotReady('Preview has no continuation')
                params['cursor'] = page.next_cursor
