"""Validate exact preview pages without asserting publication or evidence readiness.

Diagnostics are required input, never inferred from missing evidence. The future
trusted publication reader must establish their frozen provenance. These models
and assemblers do not read data, authenticate users or enable a preview endpoint.
"""

from datetime import date
from decimal import Decimal
import re

from pydantic import ConfigDict, Field, field_validator, model_validator
from typing import Literal

from trinity.auth.schemas import Publication, StrictModel
from trinity.catalog.registry import describe_dataset
from trinity.catalog.schemas import Column, DatasetKey, utc_timestamp
from trinity.connector.validate import DIAGNOSTIC_SCOPES, MESSAGES
from trinity.contracts.datasets import DATASETS
from trinity.errors import Problem
from trinity.queries.cursors import CursorCodec
from trinity.queries.preview import (
    PUBLIC_DATASETS, ResolvedPreview, key_order, source_id, strict_date, validate_key,
)

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
DECIMAL_TEXT = re.compile(r'-?(?:0|[1-9][0-9]{0,17})\.[0-9]{6}')


class PreviewRange(StrictModel):
    """Keep the resolved inclusive range, even outside publication coverage."""
    start: date
    end: date
    model_config = ConfigDict(revalidate_instances='always')

    @field_validator('start', 'end', mode='before')
    @classmethod
    def exact_dates(cls, value):
        return strict_date(value) if isinstance(value, str) else value

    @model_validator(mode='after')
    def ordered(self):
        if not 0 <= (self.end - self.start).days < 366:
            raise ValueError('Invalid preview range')
        return self


class PreviewDiagnostic(StrictModel):
    """Expose only registered public summaries with safe canonical messages."""
    model_config = ConfigDict(revalidate_instances='always')
    code: str = Field(pattern=r'^D[0-9]{2}$')
    severity: Literal['info', 'warning']
    scope: Literal['national', 'facility', 'generator', 'all']
    message: str = Field(max_length=512)
    affected_count: str = Field(pattern=r'^(0|[1-9][0-9]*)$')

    @model_validator(mode='after')
    def registered_summary(self):
        if (self.code not in DIAGNOSTIC_SCOPES or self.code == 'D09'
                or self.scope not in DIAGNOSTIC_SCOPES[self.code]
                or self.message != MESSAGES[self.code]
                or self.severity != ('info' if self.code in ('D07', 'D08') else 'warning')):
            raise ValueError('Invalid preview diagnostic')
        return self


def _check_cells(dataset, rows):
    columns = describe_dataset(dataset).columns
    for row in rows:
        if type(row) is not list or len(row) != len(columns):
            raise ValueError('Invalid preview row')
        for cell, column in zip(row, columns):
            if cell is None:
                if not column.nullable:
                    raise ValueError('Invalid preview null')
                continue
            if type(cell) is not str:
                raise ValueError('Invalid preview cell')
            cell.encode('utf-8')
            if column.type == 'date':
                strict_date(cell)
            elif column.type == 'decimal':
                if len(cell) > 26 or DECIMAL_TEXT.fullmatch(cell) is None:
                    raise ValueError('Invalid preview decimal')
                if column.name == 'capacity' and Decimal(cell) < 0:
                    raise ValueError('Invalid preview capacity')
            elif column.name in ('facility', 'generator'):
                source_id(cell)
            elif not cell.strip():
                raise ValueError('Invalid preview label')


def _row_keys(request, rows, *, after=None):
    indices = [DATASETS[request.dataset].schema.get_field_index(name)
               for name in DATASETS[request.dataset].key_fields]
    previous = key_order(validate_key(request, after)) if after is not None else None
    keys = []
    for row in rows:
        key = validate_key(request, [row[index] for index in indices])
        order = key_order(key)
        if previous is not None and order <= previous:
            raise ValueError('Invalid preview order')
        keys.append(key)
        previous = order
    return keys


class PreviewResponse(StrictModel):
    """Reject schema, ordering, privacy and response-size inconsistencies."""
    publication: Publication
    dataset_key: DatasetKey
    range: PreviewRange
    columns: list[Column] = Field(min_length=4, max_length=7)
    rows: list[list[str | None]] = Field(max_length=1000, repr=False)
    returned_rows: int = Field(ge=0, le=1000)
    next_cursor: str | None = Field(max_length=4096, repr=False)
    reason: Literal['not_reported'] | None
    diagnostics: list[PreviewDiagnostic] = Field(max_length=32)

    @field_validator('publication')
    @classmethod
    def consistent_publication(cls, value):
        value = Publication.model_validate(value.model_dump())
        if not value.coverage_start <= value.latest_observation_date <= value.coverage_end:
            raise ValueError('Invalid preview publication')
        return value.model_copy(update={'published_at': utc_timestamp(value.published_at)})

    @field_validator('next_cursor')
    @classmethod
    def cursor_shape(cls, value):
        # Authenticity is checked by the codec; the public model checks its wire form.
        if value is not None and re.fullmatch(r'pv1\.[A-Za-z0-9_-]{1,32}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}', value) is None:
            raise ValueError('Invalid preview cursor')
        return value

    @model_validator(mode='after')
    def consistent_page(self):
        dataset = PUBLIC_DATASETS[self.dataset_key]
        if self.columns != describe_dataset(dataset).columns or self.returned_rows != len(self.rows):
            raise ValueError('Invalid preview schema/count')
        if self.rows:
            if self.reason is not None:
                raise ValueError('Invalid preview reason')
        elif self.reason != 'not_reported' or self.next_cursor is not None:
            raise ValueError('Invalid empty preview')
        _check_cells(dataset, self.rows)
        request = ResolvedPreview(dataset, self.range.start, self.range.end)
        _row_keys(request, self.rows)
        for row in self.rows:
            if not self.publication.coverage_start <= strict_date(row[0]) <= self.publication.coverage_end:
                raise ValueError('Invalid observation coverage')
        if (any(item.scope != dataset for item in self.diagnostics)
                or len({(item.code, item.scope) for item in self.diagnostics}) != len(self.diagnostics)):
            raise ValueError('Invalid preview diagnostic scope')
        if len(self.model_dump_json().encode('utf-8')) > MAX_RESPONSE_BYTES:
            raise ValueError('Preview response exceeds byte limit')
        return self


def serialize_preview_rows(dataset: str, rows: list[list]) -> list[list[str | None]]:
    """Encode native Arrow-style values exactly; never round or convert floats."""
    try:
        if dataset not in DATASETS or type(rows) is not list or len(rows) > 1001:
            raise ValueError
        columns = describe_dataset(dataset).columns
        result = []
        for row in rows:
            if type(row) is not list or len(row) != len(columns):
                raise ValueError
            encoded = []
            for value, column in zip(row, columns):
                if value is None:
                    encoded.append(None)
                elif column.type == 'decimal':
                    if not isinstance(value, Decimal) or not value.is_finite() or value.copy_abs() >= Decimal('1e18'):
                        raise ValueError
                    text = format(value, '.6f')
                    if Decimal(text) != value:
                        raise ValueError
                    encoded.append(text)
                elif column.type == 'date':
                    if type(value) is not date:
                        raise ValueError
                    encoded.append(value.isoformat())
                else:
                    if type(value) is not str:
                        raise ValueError
                    encoded.append(value)
            result.append(encoded)
        _check_cells(dataset, result)
        return result
    except (ValueError, TypeError, KeyError, ArithmeticError):
        raise Problem(503, 'dependency_unavailable') from None


def build_preview_response(request: ResolvedPreview, publication: Publication,
                           rows: list[list[str | None]], *, diagnostics: list[PreviewDiagnostic],
                           codec: CursorCodec, after=None) -> PreviewResponse:
    """Assemble a bounded wire page from at most limit+1 already encoded rows.

    Explicit diagnostics come from a future trusted evidence reader; accepting
    this argument does not prove its provenance. No publication is activated.
    """
    try:
        if type(rows) is not list or len(rows) > request.limit + 1 or after is not None and not rows:
            raise ValueError
        _check_cells(request.dataset, rows)
        keys = _row_keys(request, rows, after=after)
        if any(not publication.coverage_start <= strict_date(row[0]) <= publication.coverage_end for row in rows):
            raise ValueError
        next_cursor = None
        if len(rows) > request.limit:
            next_cursor = codec.encode(request, publication.publication_event_id, keys[request.limit - 1])
        returned = rows[:request.limit]
        # Bound the complete envelope before model validation so size has its public code.
        body = dict(publication=publication, dataset_key=DATASETS[request.dataset].table_name,
                    range=PreviewRange(start=request.start, end=request.end),
                    columns=describe_dataset(request.dataset).columns, rows=returned,
                    returned_rows=len(returned), next_cursor=next_cursor,
                    reason=None if returned else 'not_reported', diagnostics=diagnostics)
        draft = PreviewResponse.model_construct(**body)
        if len(draft.model_dump_json(warnings='error').encode('utf-8')) > MAX_RESPONSE_BYTES:
            raise Problem(503, 'query_resource_limit')
        return PreviewResponse.model_validate(body)
    except Problem:
        raise
    except (ValueError, TypeError, KeyError, IndexError, ArithmeticError):
        raise Problem(503, 'dependency_unavailable') from None
