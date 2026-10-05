"""Read a leap-year national fixture with real DataFusion and exact Parquet cells."""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from trinity.catalog.schemas import Freshness
from trinity.contracts.queries import PreviewOperation
from trinity.dashboard.calculation import build_dashboard, build_metric
from trinity.dashboard.service import RefusingCodec
from trinity.queries.preview_schemas import build_preview_batch_response
from trinity.queries.runtime.preview import execute_preview
from sql_fixture import write_table
from test_preview_unit import publication


class DashboardEngineTests(unittest.TestCase):
    def test_366_dates_exact_values_interior_and_end_gaps_and_metric_agreement(self):
        """Missing rows stay absent in Parquet but become null display points."""
        first, last = date(2024, 1, 1), date(2024, 12, 31)
        # Include leap day, negative zero rounding, zero capacity and a ratio
        # just below a rounding boundary. Missing March 1 and year end test gaps.
        special = {
            0: ('1000.000000', '-0.001000'),
            1: ('0.000000', '0.000000'),
            2: ('1000.000000', '0.000000'),
            59: ('1000.000000', '-123.450000'),
            61: ('999999999999980000.000001', '49999999999999.000000'),
        }
        values = []
        for offset in range(366):
            if offset in (60, 365):
                continue
            capacity, outage = special.get(offset, ('1000.000000', '125.000000'))
            values.append(dict(period=first+timedelta(days=offset), capacity=Decimal(capacity),
                               outage=Decimal(outage), percentOutage=None))
        public = publication(coverage_start=first, coverage_end=last, latest_observation_date=last)
        operation = PreviewOperation('national', str(public.publication_event_id), str(public.version_id),
                                     first.isoformat(), last.isoformat(), page_size=366)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_table(root, count=len(values), values=values)
            batch = execute_preview(operation, root)
            self.assertEqual(len(batch['rows']), 364)
            self.assertFalse(batch['has_more'])
            preview = build_preview_batch_response(operation, public, batch, diagnostics=[], codec=RefusingCodec())
            result = build_dashboard(preview, Freshness(latest_observation_date=last,
                                                       published_at=public.published_at, last_refresh=None))
            self.assertEqual(len(result.days), 366)
            self.assertEqual(result.days[0].offline_share_percent, '0.00')
            self.assertEqual(result.days[1].reason, 'zero_capacity')
            self.assertEqual(result.days[2].offline_share_percent, '0.00')
            self.assertIsNone(result.days[2].reason)
            self.assertEqual(result.days[59].period, date(2024, 2, 29))
            self.assertEqual(result.days[59].offline_share_percent, '-12.35')
            self.assertEqual(result.days[60].reason, 'not_reported')
            self.assertEqual(result.days[61].capacity, '999999999999980000.000001')
            self.assertEqual(result.days[61].offline_share_percent, '0.00')
            self.assertEqual(result.summary, result.days[-1])
            self.assertEqual(result.summary.reason, 'not_reported')
            # Execute independent one-day reads for every selected date. Comparing
            # only the already built array would not test runtime date predicates.
            for point in result.days:
                day = point.period.isoformat()
                metric_op = PreviewOperation('national', str(public.publication_event_id),
                                             str(public.version_id), day, day, page_size=1)
                page = build_preview_batch_response(metric_op, public, execute_preview(metric_op, root),
                                                    diagnostics=[], codec=RefusingCodec())
                metric = build_metric(page)
                self.assertEqual((metric.metric.value, metric.metric.reason),
                                 (point.offline_share_percent, point.reason))
