"""Validate preview inputs without reading publication state or analytical files.

Primitive parsing precedes the shared rate debit. Semantic validation and
publication-based defaults follow it. These helpers never authenticate a caller
or reserve execution capacity; the service enforces that ordering.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
import re
from types import MappingProxyType

from trinity.auth.permissions import Principal, require, require_dataset
from trinity.contracts.datasets import DATASETS
from trinity.errors import Problem

PUBLIC_DATASETS = MappingProxyType({value.table_name: key for key, value in DATASETS.items()})
PARAMETERS = frozenset(('start', 'end', 'facility', 'generator', 'limit', 'cursor'))


def strict_date(value: str) -> date:
    """Accept one exact ISO calendar date, without datetime/coercion shortcuts."""
    if type(value) is not str or re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is None:
        raise ValueError('Invalid date')
    return date.fromisoformat(value)


def source_id(value: str) -> str:
    """Validate a source identifier while preserving every supplied character."""
    if type(value) is not str or not 1 <= len(value) <= 128 or not value.strip():
        raise ValueError('Invalid identifier')
    value.encode('utf-8')
    return value


def _range(start, end):
    if type(start) is not date or type(end) is not date or not 0 <= (end - start).days < 366:
        raise ValueError('Invalid range')


def _filters(dataset, facility, generator):
    if dataset not in DATASETS:
        raise ValueError('Invalid dataset')
    for value in (facility, generator):
        if value is not None:
            source_id(value)
    if (dataset == 'national' and (facility is not None or generator is not None)
            or generator is not None and (dataset != 'generator' or facility is None)):
        raise ValueError('Invalid filters')


def authorize_preview(principal: Principal, dataset_key: str) -> str:
    """Resolve public names through current shared authority before any data work."""
    dataset = PUBLIC_DATASETS.get(dataset_key) if type(dataset_key) is str else None
    require_dataset(principal, dataset)
    require(principal, 'preview:national' if dataset == 'national' else 'preview:detail')
    return dataset


@dataclass(frozen=True, repr=False)
class PreviewInput:
    """Hold primitive parsed input; semantic filters have not passed yet."""
    start: date | None = None
    end: date | None = None
    facility: str | None = None
    generator: str | None = None
    limit: int = 100
    cursor: str | None = field(default=None, repr=False)

    def __post_init__(self):
        try:
            if any(v is not None and type(v) is not date for v in (self.start, self.end)):
                raise ValueError
            for value in (self.facility, self.generator):
                if value is not None:
                    source_id(value)
            if type(self.limit) is not int or not 1 <= self.limit <= 1000:
                raise ValueError
            if self.cursor is not None:
                if type(self.cursor) is not str or not 1 <= len(self.cursor) <= 4096 or not self.cursor.strip():
                    raise ValueError
                self.cursor.encode('utf-8')
        except (ValueError, TypeError, UnicodeError):
            raise Problem(422, 'invalid_request') from None


@dataclass(frozen=True, repr=False)
class ResolvedPreview:
    """Hold one complete typed preview tuple, independent of storage authority."""
    dataset: str
    start: date
    end: date
    facility: str | None = None
    generator: str | None = None
    limit: int = 100

    def __post_init__(self):
        try:
            _filters(self.dataset, self.facility, self.generator)
            _range(self.start, self.end)
            if type(self.limit) is not int or not 1 <= self.limit <= 1000:
                raise ValueError
        except (ValueError, TypeError):
            raise Problem(422, 'invalid_request') from None


def parse_preview_input(pairs, *, body: bytes = b'') -> PreviewInput:
    """Parse already URL-decoded pairs before a rate debit, retaining duplicates.

    The HTTP adapter must pass all pairs, not a collapsed dict. No second URL
    decode occurs here. This function performs no semantic cross-field checks.
    """
    try:
        if type(body) is not bytes or body or isinstance(pairs, (str, bytes, dict)):
            raise ValueError
        values = {}
        for index, pair in enumerate(pairs):
            if index >= len(PARAMETERS) or not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError
            name, value = pair
            if (type(name) is not str or name not in PARAMETERS or name in values
                    or type(value) is not str or not value or not value.strip()):
                raise ValueError
            if name in ('start', 'end'):
                value = strict_date(value)
            elif name in ('facility', 'generator'):
                value = source_id(value)
            elif name == 'limit':
                if len(value) > 4 or re.fullmatch(r'[1-9][0-9]*', value) is None:
                    raise ValueError
                value = int(value)
            values[name] = value
        return PreviewInput(**values)
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise Problem(422, 'invalid_request') from None


def validate_filters(dataset: str, request: PreviewInput) -> None:
    """Reject semantic combinations after the service commits its debit."""
    try:
        _filters(dataset, request.facility, request.generator)
        if request.start is not None and request.end is not None:
            _range(request.start, request.end)
    except (ValueError, TypeError):
        raise Problem(422, 'invalid_request') from None


def resolve_preview(dataset: str, request: PreviewInput, latest_observation: date) -> ResolvedPreview:
    """Resolve each missing bound from supplied pinned metadata, without I/O."""
    validate_filters(dataset, request)
    try:
        if type(latest_observation) is not date:
            raise ValueError
        start = request.start if request.start is not None else latest_observation - timedelta(days=29)
        end = request.end if request.end is not None else latest_observation
    except (ValueError, OverflowError):
        raise Problem(503, 'dependency_unavailable') from None
    return ResolvedPreview(dataset, start, end, request.facility, request.generator, request.limit)


def validate_key(request: ResolvedPreview, key) -> tuple[str, ...]:
    """Check the entire continuation key against the resolved request predicates."""
    if type(key) not in (list, tuple) or len(key) != len(DATASETS[request.dataset].key_fields):
        raise ValueError('Invalid key')
    period = strict_date(key[0])
    if not request.start <= period <= request.end:
        raise ValueError('Invalid key')
    for value in key[1:]:
        source_id(value)
    if request.facility is not None and key[1] != request.facility:
        raise ValueError('Invalid key')
    if request.generator is not None and key[2] != request.generator:
        raise ValueError('Invalid key')
    return tuple(key)


def key_order(key: tuple[str, ...]) -> tuple:
    """Compare complete daily keys with binary UTF-8 ordering for source IDs."""
    return (strict_date(key[0]), *(value.encode('utf-8') for value in key[1:]))
