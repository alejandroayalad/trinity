"""Turn decoded parameters and validated national previews into pure responses.

Parse primitive shapes before the caller debits a request. Check combinations
after that debit, then resolve presets from the pinned latest observation.
Build one point per requested date and calculate with exact fractions. Missing
rows remain null. Invalid input raises 422; broken preview data raises 503.
Inputs are retained unchanged. No helper authenticates, reads storage or runs SQL.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from trinity.catalog.schemas import Freshness
from trinity.dashboard.schemas import (
    DashboardResponse, DateRange, MetricResponse, MetricValue, NationalDay,
)
from trinity.errors import Problem
from trinity.queries.preview import strict_date
from trinity.queries.preview_schemas import PreviewResponse

PRESETS = {'30d': 30, '90d': 90, '1y': 365}


@dataclass(frozen=True)
class DashboardInput:
    """Retain primitive values without applying post-debit combination rules."""
    preset: str | None = None
    start: date | None = None
    end: date | None = None


@dataclass(frozen=True)
class MetricInput:
    """Retain the required, strictly parsed metric date."""
    period: date


def _parse(pairs, body, allowed):
    """Inspect all decoded occurrences before making a scalar mapping."""
    try:
        if type(body) is not bytes or body or isinstance(pairs, (str, bytes, dict)):
            raise ValueError
        values = {}
        for index, pair in enumerate(pairs):
            if index >= len(allowed) or not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError
            name, value = pair
            if (type(name) is not str or name not in allowed or name in values
                    or type(value) is not str or not value.strip()):
                raise ValueError
            if name == 'preset':
                if value not in PRESETS:
                    raise ValueError
            else:
                value = strict_date(value)
            values[name] = value
        return values
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise Problem(422, 'invalid_request') from None


def parse_dashboard_input(pairs, *, body=b'') -> DashboardInput:
    """Reject malformed shapes before rate accounting; preserve combinations."""
    return DashboardInput(**_parse(pairs, body, {'preset', 'start', 'end'}))


def parse_metric_input(pairs, *, body=b'') -> MetricInput:
    """Require one period and no other input, before rate accounting."""
    values = _parse(pairs, body, {'period'})
    if 'period' not in values:
        raise Problem(422, 'invalid_request')
    return MetricInput(**values)


def validate_dashboard_input(request: DashboardInput) -> None:
    """Reject incompatible dates after the caller commits its rate debit."""
    try:
        if request.preset is not None and (request.start is not None or request.end is not None):
            raise ValueError
        if (request.start is None) != (request.end is None):
            raise ValueError
        if request.start is not None:
            DateRange(start=request.start, end=request.end)
    except (ValueError, TypeError):
        raise Problem(422, 'invalid_request') from None


def resolve_range(request: DashboardInput, latest_observation: date) -> DateRange:
    """Resolve inclusive presets from publication metadata, never today's date."""
    validate_dashboard_input(request)
    if request.start is not None:
        return DateRange(start=request.start, end=request.end)
    try:
        if type(latest_observation) is not date:
            raise ValueError
        # Subtract N-1 because both bounds belong to the selected range.
        count = PRESETS[request.preset or '30d']
        return DateRange(start=latest_observation - timedelta(days=count - 1), end=latest_observation)
    except (ValueError, TypeError, KeyError, OverflowError):
        raise Problem(503, 'dependency_unavailable') from None


def offline_share(capacity: str, outage: str) -> tuple[str | None, str | None]:
    """Round the exact percent half away from zero, without decimal division.

    Fraction stores a ratio as integers. It has no precision context, so even
    a ratio just below a half-cent boundary cannot round up by accident.
    Capacity zero has no defined metric. Negative outage remains meaningful.
    """
    try:
        if type(capacity) is not str or type(outage) is not str:
            raise ValueError
        capacity_value, outage_value = Decimal(capacity), Decimal(outage)
        if not capacity_value.is_finite() or not outage_value.is_finite() or capacity_value < 0:
            raise ValueError
        if capacity_value == 0:
            return None, 'zero_capacity'
        # Work in hundredths of a percent. Round only the integer remainder.
        ratio = Fraction(outage_value) * 10000 / Fraction(capacity_value)
        whole, remainder = divmod(abs(ratio.numerator), ratio.denominator)
        rounded = whole + (2 * remainder >= ratio.denominator)
        # -0.0001 percent becomes zero hundredths. A zero has no minus sign.
        sign = '-' if ratio < 0 and rounded else ''
        return f'{sign}{rounded // 100}.{rounded % 100:02d}', None
    except (ValueError, TypeError, ArithmeticError):
        raise Problem(503, 'dependency_unavailable') from None


def build_points(start: date, end: date, rows: list[list[str | None]]) -> list[NationalDay]:
    """Fill display gaps without changing or fabricating stored source rows."""
    try:
        selected = DateRange(start=start, end=end)
        by_date = {}
        previous = None
        for row in rows:
            period, capacity, outage, percent = row
            day = strict_date(period)
            if not start <= day <= end or previous is not None and day <= previous:
                raise ValueError
            value, reason = offline_share(capacity, outage)
            by_date[day] = NationalDay(period=day, capacity=capacity, outage=outage,
                                      percentOutage=percent, offline_share_percent=value, reason=reason)
            previous = day
        points = []
        # Iterate offsets, so a range ending at date.max never adds past it.
        for offset in range((selected.end - selected.start).days + 1):
            day = start + timedelta(days=offset)
            point = by_date.get(day)
            if point is None:
                point = NationalDay(period=day, capacity=None, outage=None, percentOutage=None,
                                    offline_share_percent=None, reason='not_reported')
            points.append(point)
        return points
    except (ValueError, TypeError, ArithmeticError):
        raise Problem(503, 'dependency_unavailable') from None


def _national_preview(preview):
    """Revalidate the complete page; a cursor means the read was incomplete."""
    preview = PreviewResponse.model_validate(preview.model_dump())
    if preview.dataset_key != 'national_outages' or preview.next_cursor is not None:
        raise ValueError('Invalid national preview')
    return preview


def build_dashboard(preview: PreviewResponse, freshness: Freshness) -> DashboardResponse:
    """Build cards from the last selected day, even when that date is absent."""
    try:
        preview = _national_preview(preview)
        points = build_points(preview.range.start, preview.range.end, preview.rows)
        return DashboardResponse(publication=preview.publication,
                                 range=DateRange(**preview.range.model_dump()), days=points,
                                 summary=points[-1], diagnostics=preview.diagnostics, freshness=freshness)
    except (ValueError, TypeError, ArithmeticError):
        raise Problem(503, 'dependency_unavailable') from None


def build_metric(preview: PreviewResponse) -> MetricResponse:
    """Use the dashboard point builder for exactly one requested date."""
    try:
        preview = _national_preview(preview)
        if preview.range.start != preview.range.end:
            raise ValueError('Metric requires one date')
        point = build_points(preview.range.start, preview.range.end, preview.rows)[0]
        return MetricResponse(publication=preview.publication, period=point.period,
                              metric=MetricValue(value=point.offline_share_percent, reason=point.reason),
                              diagnostics=preview.diagnostics)
    except (ValueError, TypeError, ArithmeticError):
        raise Problem(503, 'dependency_unavailable') from None
