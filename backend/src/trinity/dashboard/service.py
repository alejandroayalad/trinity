"""Read a bounded national page through the existing isolated execution path.

Public input supplies a preset or two calendar bounds. Reuse preview admission,
publication pinning, national-only staging and confirmed container cleanup.
Then add missing display dates and calculate exact shares. No source row changes,
no EIA request occurs, and any execution failure returns no partial dashboard.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext

from trinity.catalog.schemas import Freshness, LastRefresh
from trinity.errors import Problem
from trinity.queries.preview import PreviewInput, ResolvedPreview, strict_date
from trinity.queries.service import PreviewService
from trinity.refresh.repository import read_last_refresh


@dataclass(frozen=True, repr=False)
class NationalInput(PreviewInput):
    """Retain preset intent until the publication supplies its latest date."""
    preset: str | None = None


def parse_national(pairs, *, body=b'', metric=False):
    """Reject duplicate/unknown fields and malformed primitive values before debit."""
    allowed = {'period'} if metric else {'preset', 'start', 'end'}
    values = {}
    try:
        if body or isinstance(pairs, (str, bytes, dict)):
            raise ValueError
        for key, value in pairs:
            if key not in allowed or key in values or type(value) is not str or not value:
                raise ValueError
            values[key] = strict_date(value) if key != 'preset' else value
        if metric:
            if set(values) != {'period'}:
                raise ValueError
            return NationalInput(start=values['period'], end=values['period'], limit=366)
        if 'preset' in values and values['preset'] not in ('30d', '90d', '1y'):
            raise ValueError
        return NationalInput(**values, limit=366)
    except (ValueError, TypeError, OverflowError):
        raise Problem(422, 'invalid_request') from None


def metric_value(outage, capacity):
    """Calculate one daily share. Keep source values and signed shares unchanged."""
    if outage is None or capacity is None:
        return {'value': None, 'reason': 'not_reported'}
    with localcontext() as context:
        # Inputs allow 24 digits. The extra precision preserves small denominators
        # and half-up ties without using the process decimal context.
        context.prec = 80
        denominator = Decimal(capacity)
        if denominator == 0:
            return {'value': None, 'reason': 'zero_capacity'}
        value = (Decimal(outage) * 100 / denominator).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        return {'value': format(value, '.2f'), 'reason': None}


def dashboard_from_preview(page, freshness):
    """Require the complete bounded national page before creating display gaps."""
    if page.dataset_key != 'national_outages' or page.next_cursor is not None:
        raise Problem(503, 'dependency_unavailable')
    rows = {row[0]: dict(zip((c.name for c in page.columns), row)) for row in page.rows}
    days = []
    for offset in range((page.range.end - page.range.start).days + 1):
        period = (page.range.start + timedelta(days=offset)).isoformat()
        row = rows.get(period, {})
        metric = metric_value(row.get('outage'), row.get('capacity'))
        days.append(dict(period=period, capacity=row.get('capacity'), outage=row.get('outage'),
                         percentOutage=row.get('percentOutage'), offline_share_percent=metric['value'],
                         reason=metric['reason']))
    return dict(publication=page.publication, range=page.range, summary=days[-1],
                days=days, diagnostics=page.diagnostics, freshness=freshness)


class NationalService(PreviewService):
    """Specialize only national input and response; keep shared execution controls."""
    def __init__(self, *args, metric=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.metric = metric

    def authorize(self, principal, dataset_key):
        """Require national read authority on both identity checks."""
        from trinity.auth.permissions import require
        require(principal, 'national:read')
        return super().authorize(principal, dataset_key)

    def parse_input(self, pairs, *, body):
        """Parse the selected route's closed parameter grammar."""
        return parse_national(pairs, body=body, metric=self.metric)

    def validate_input(self, dataset, request):
        """Reject mixed presets and custom ranges after one committed debit."""
        if (dataset != 'national' or (request.start is None) != (request.end is None)
                or request.preset is not None and request.start is not None):
            raise Problem(422, 'invalid_request')
        if request.start is not None and not 0 <= (request.end - request.start).days < 366:
            raise Problem(422, 'invalid_request')

    def resolve_input(self, dataset, request, latest):
        """Resolve presets from one pinned latest observation without clipping."""
        count = {'30d': 30, '90d': 90, '1y': 365}[request.preset or '30d']
        try:
            return ResolvedPreview('national', request.start or latest - timedelta(days=count - 1),
                                   request.end or latest, limit=366)
        except OverflowError:
            raise Problem(422, 'invalid_request') from None

    def read_context(self, connection, pinned):
        """Pin only public refresh status/times alongside the publication."""
        row = read_last_refresh(connection)
        return Freshness(latest_observation_date=pinned.publication.latest_observation_date,
                         published_at=pinned.publication.published_at,
                         last_refresh=LastRefresh(**row) if row else None)

    def national(self, token, pairs, *, body=b'', cancelled=None):
        """Return national values only after the shared supervisor finishes cleanup."""
        prepared, execution = self.prepare(token, 'national_outages', pairs, body=body, cancelled=cancelled)
        page = execution.execute(prepared)
        result = dashboard_from_preview(page, prepared.context)
        if self.metric:
            summary = result['summary']
            return dict(publication=page.publication, period=summary['period'],
                        metric={'value': summary['offline_share_percent'], 'reason': summary['reason']},
                        diagnostics=page.diagnostics)
        return result
