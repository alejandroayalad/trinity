"""Check synthetic national calculations without database, storage or execution."""
from datetime import date, timedelta
from decimal import localcontext
import copy
import json
from pathlib import Path
import unittest
from pydantic import ValidationError
from trinity.catalog.schemas import Freshness
from trinity.dashboard.calculation import (
    build_dashboard, build_metric, build_points, offline_share,
    parse_dashboard_input, parse_metric_input, resolve_range, validate_dashboard_input,
)
from trinity.dashboard.schemas import DashboardResponse, DateRange, MetricResponse, MetricValue, NationalDay
from trinity.queries.preview import ResolvedPreview
from test_preview_unit import SafeAssertions, page, publication

LATEST = date(2026, 10, 2)


def freshness():
    """Use the shared synthetic publication's observation and publication dates."""
    public = publication()
    return Freshness(latest_observation_date=public.latest_observation_date,
                     published_at=public.published_at, last_refresh=None)


def national_page(start=date(2026, 9, 29), end=LATEST, rows=None):
    """Validate synthetic source rows through the real preview response builder."""
    if rows is None:
        rows = [['2026-09-29', '1000.000000', '123.450000', None],
                ['2026-10-01', '0.000000', '0.000000', '0.000000']]
    return page(ResolvedPreview('national', start, end, limit=(end-start).days+1), rows)


class DashboardInputTests(SafeAssertions):
    def test_d01_date_table(self):
        cases = [([], '2026-09-03', '2026-10-02', 30),
                 ([('preset', '30d')], '2026-09-03', '2026-10-02', 30),
                 ([('preset', '90d')], '2026-07-05', '2026-10-02', 90),
                 ([('preset', '1y')], '2025-10-03', '2026-10-02', 365),
                 ([('start', '2024-01-01'), ('end', '2024-12-31')], '2024-01-01', '2024-12-31', 366)]
        for pairs, start, end, count in cases:
            with self.subTest(pairs=pairs):
                result = resolve_range(parse_dashboard_input(pairs), LATEST)
                self.assertEqual((str(result.start), str(result.end)), (start, end))
                self.assertEqual((result.end-result.start).days+1, count)

    def test_bad_shapes_both_endpoints(self):
        for parser, key in ((parse_dashboard_input, 'start'), (parse_metric_input, 'period')):
            for value in ('', ' ', '20261002', '2026-1-02', '2026-10-2', '2026-02-29',
                          '2024-02-30', '2026-10-02T00:00:00', '2026-10-02Z',
                          ' 2026-10-02', '2026-10-02 ', '２０２６-10-02', '0000-01-01',
                          '2026%2D10%2D02', None, 20261002):
                with self.subTest(parser=parser.__name__, value=value):
                    self.problem('invalid_request', parser, [(key, value)], status=422)
            for pairs in ([(key, '2026-10-02')]*2, [('unknown', 'x')],
                          [(key.upper(), '2026-10-02')], [(key,)], 'period=x', {}, None):
                self.problem('invalid_request', parser, pairs)
            for body in (b'{}', b' ', '', None):
                self.problem('invalid_request', parser, [(key, '2026-10-02')], body=body)
        for value in ('30D', '365d', 'custom', ' 30d', ''):
            self.problem('invalid_request', parse_dashboard_input, [('preset', value)])
        self.problem('invalid_request', parse_metric_input, [])
        self.problem('invalid_request', parse_metric_input, [('preset', '30d')])
        self.problem('invalid_request', parse_dashboard_input, [('period', '2026-10-02')])

    def test_combinations_pass_shape_but_fail_after_debit_boundary(self):
        cases = [[('preset', '30d'), ('start', '2026-10-01')],
                 [('preset', '90d'), ('end', '2026-10-02')],
                 [('preset', '1y'), ('start', '2026-10-01'), ('end', '2026-10-02')],
                 [('start', '2026-10-01')], [('end', '2026-10-02')],
                 [('start', '2026-10-02'), ('end', '2026-10-01')],
                 [('start', '2024-01-01'), ('end', '2025-01-01')]]
        for pairs in cases:
            parsed = parse_dashboard_input(pairs)
            self.problem('invalid_request', validate_dashboard_input, parsed)
            self.problem('invalid_request', resolve_range, parsed, LATEST)

    def test_leap_calendar_and_yearly_preset_is_365_dates(self):
        for text in ('2000-02-29', '2024-02-29', '9999-12-31'):
            self.assertEqual(parse_metric_input([('period', text)]).period, date.fromisoformat(text))
        for text in ('1900-02-29', '2100-02-29'):
            self.problem('invalid_request', parse_metric_input, [('period', text)])
        selected = resolve_range(parse_dashboard_input([('preset', '1y')]), date(2024, 12, 31))
        self.assertEqual(selected.start, date(2024, 1, 2))
        points = build_points(date(2024, 1, 1), date(2024, 12, 31), [])
        self.assertEqual(len(points), 366)
        self.assertEqual(points[59].period, date(2024, 2, 29))
        self.assertEqual(build_points(date.max, date.max, [])[0].period, date.max)

    def test_custom_bounds_never_clamp_to_publication(self):
        for start, end in (('2020-01-01', '2020-01-02'), ('2026-10-01', '2026-10-04'),
                           ('2030-01-01', '2030-01-01')):
            selected = resolve_range(parse_dashboard_input([('start', start), ('end', end)]), LATEST)
            self.assertEqual((str(selected.start), str(selected.end)), (start, end))
        for latest in (None, date.min):
            self.problem('dependency_unavailable', resolve_range, parse_dashboard_input([]), latest)


class DashboardCalculationTests(SafeAssertions):
    def test_every_d02_row(self):
        for capacity, outage, expected in (
            ('1000', '125', ('12.50', None)), ('2108.4', '863.4', ('40.95', None)),
            ('1000', '123.45', ('12.35', None)), ('1000', '-123.45', ('-12.35', None)),
            ('1000', '-0.001', ('0.00', None)), ('0', '0', (None, 'zero_capacity')),
        ):
            with self.subTest(capacity=capacity, outage=outage):
                self.assertEqual(offline_share(capacity, outage), expected)

    def test_exact_near_half_values_ignore_decimal_context(self):
        # These fit DECIMAL(24,6). The first ratio is just below 0.005 percent.
        # Limited decimal division can erase that difference and round it up.
        cases = [('999999999999980000.000001', '49999999999999.000000', '0.00'),
                 ('999999999999980000.000000', '49999999999999.000000', '0.01'),
                 ('999999999999979999.999999', '49999999999999.000000', '0.01'),
                 ('0.000001', '999999999999999999.999999', '99999999999999999999999900.00'),
                 ('3.000000', '1.000000', '33.33')]
        with localcontext() as context:
            context.prec = 3
            for capacity, outage, expected in cases:
                self.assertEqual(offline_share(capacity, outage), (expected, None))
                signed = '0.00' if expected == '0.00' else '-'+expected
                self.assertEqual(offline_share(capacity, '-'+outage), (signed, None))

    def test_zero_capacity_differs_from_zero_outage_and_values_are_not_clamped(self):
        for capacity, outage, expected in (('0', '5', (None, 'zero_capacity')),
                                          ('100', '0', ('0.00', None)),
                                          ('100', '-0', ('0.00', None)),
                                          ('100', '150', ('150.00', None)),
                                          ('100', '-150', ('-150.00', None))):
            self.assertEqual(offline_share(capacity, outage), expected)
        for capacity, outage in (('-1', '1'), ('NaN', '1'), ('1', 'Infinity'), (1.0, '1')):
            self.problem('dependency_unavailable', offline_share, capacity, outage)

    def test_gaps_and_end_summary_preserve_nulls_and_source_strings(self):
        preview = national_page()
        original = copy.deepcopy(preview.model_dump())
        result = build_dashboard(preview, freshness())
        self.assertEqual([p.period.day for p in result.days], [29, 30, 1, 2])
        self.assertEqual(result.days[0].capacity, '1000.000000')
        self.assertEqual(result.days[0].outage, '123.450000')
        self.assertIsNone(result.days[0].percentOutage)
        self.assertEqual(result.days[0].offline_share_percent, '12.35')
        self.assertEqual(result.days[2].reason, 'zero_capacity')
        self.assertEqual(result.summary, result.days[-1])
        self.assertEqual(result.summary.reason, 'not_reported')
        self.assertIsNone(result.summary.capacity)
        self.assertEqual(preview.model_dump(), original)

    def test_metric_equals_every_dashboard_date_including_absent_and_zero(self):
        preview = national_page()
        dashboard = build_dashboard(preview, freshness())
        for point in dashboard.days:
            rows = [row for row in preview.rows if row[0] == point.period.isoformat()]
            metric = build_metric(national_page(point.period, point.period, rows))
            self.assertEqual(metric.period, point.period)
            self.assertEqual(metric.publication, dashboard.publication)
            self.assertEqual(metric.diagnostics, dashboard.diagnostics)
            self.assertEqual((metric.metric.value, metric.metric.reason),
                             (point.offline_share_percent, point.reason))

    def test_outside_coverage_is_not_reported(self):
        for start, end in ((date(2020, 1, 1), date(2020, 1, 2)),
                           (LATEST, LATEST+timedelta(days=2))):
            result = build_dashboard(national_page(start, end, []), freshness())
            self.assertTrue(all(point.reason == 'not_reported' for point in result.days))
            self.assertEqual(result.summary, result.days[-1])
        self.assertEqual(build_metric(national_page(date(2030, 1, 1), date(2030, 1, 1), [])).metric.reason,
                         'not_reported')

    def test_broken_rows_and_incomplete_preview_fail_closed(self):
        rows = national_page().rows
        for invalid in ([rows[0], rows[0]], list(reversed(rows)),
                        [['2026-09-28', *rows[0][1:]]], [rows[0][:-1]]):
            self.problem('dependency_unavailable', build_points, date(2026, 9, 29), LATEST, invalid)
        self.problem('dependency_unavailable', build_metric, national_page())
        # model_copy bypasses validation. The builder must validate it again.
        for changes in ({'rows': [rows[0], rows[0]]}, {'returned_rows': 99}, {'next_cursor': 'forged'}):
            self.problem('dependency_unavailable', build_dashboard,
                         national_page().model_copy(update=changes), freshness())


class DashboardSchemaTests(unittest.TestCase):
    def test_exact_closed_fields_and_required_members_match_openapi(self):
        schemas = json.loads((Path(__file__).parents[2]/'docs/openapi.json').read_text())['components']['schemas']
        instances = [build_dashboard(national_page(), freshness()),
                     build_metric(national_page(LATEST, LATEST, [])),
                     build_points(LATEST, LATEST, [])[0], DateRange(start=LATEST, end=LATEST),
                     MetricValue(value='12.50', reason=None)]
        for instance in instances:
            model = type(instance)
            expected = schemas[model.__name__]
            body = instance.model_dump()
            self.assertEqual(set(body), set(expected['properties']))
            self.assertEqual(set(model.model_json_schema()['required']), set(expected['required']))
            self.assertFalse(model.model_json_schema()['additionalProperties'])
            self.assertEqual(model.model_validate_json(instance.model_dump_json()), instance)
            for key in body:
                missing = dict(body)
                del missing[key]
                with self.assertRaises(ValidationError):
                    model.model_validate(missing)
            with self.assertRaises(ValidationError):
                model.model_validate({**body, 'extra': 'canary'})

    def test_days_length_order_range_and_summary(self):
        base = build_dashboard(national_page(), freshness()).model_dump()
        for changes in ({'days': []}, {'days': base['days'][:-1]}, {'days': base['days']*100},
                        {'days': list(reversed(base['days']))}, {'days': [base['days'][0]]*4},
                        {'summary': base['days'][0]}, {'range': {'start': LATEST, 'end': LATEST}},
                        {'range': {'start': LATEST, 'end': date(2026, 1, 1)}}):
            with self.assertRaises(ValidationError):
                DashboardResponse.model_validate({**base, **changes})

    def test_metric_pattern_and_reason_pairing(self):
        for value in ('-0.00', '01.00', '1', '1.0', '1.000', '+1.00', '1e2', 1.0, 'NaN'):
            with self.assertRaises(ValidationError):
                MetricValue(value=value, reason=None)
        for value, reason in ((None, None), ('0.00', 'zero_capacity'), ('1.00', 'not_reported'), (None, 'unknown')):
            with self.assertRaises(ValidationError):
                MetricValue(value=value, reason=reason)
        base = build_points(LATEST, LATEST, [])[0].model_dump()
        for changes in ({'capacity': '1'}, {'outage': '0'}, {'percentOutage': '0'},
                        {'reason': 'zero_capacity'}, {'offline_share_percent': '0.00'}):
            with self.assertRaises(ValidationError):
                NationalDay.model_validate({**base, **changes})
        present = build_dashboard(national_page(), freshness()).days[0].model_dump()
        for changes in ({'capacity': '-1'}, {'capacity': '0'}, {'outage': None},
                        {'offline_share_percent': None}, {'reason': 'zero_capacity'}):
            with self.assertRaises(ValidationError):
                NationalDay.model_validate({**present, **changes})

    def test_nested_extra_missing_fields_and_freshness_mismatch(self):
        base = build_dashboard(national_page(), freshness()).model_dump()
        for key in ('publication', 'freshness', 'range', 'summary'):
            for mutation in ('extra', 'missing'):
                body = copy.deepcopy(base)
                if mutation == 'extra':
                    body[key]['extra'] = 'canary'
                else:
                    del body[key][next(iter(body[key]))]
                with self.assertRaises(ValidationError):
                    DashboardResponse.model_validate(body)
        base['freshness']['latest_observation_date'] = date(2026, 10, 1)
        with self.assertRaises(ValidationError):
            DashboardResponse.model_validate(base)


if __name__ == '__main__':
    unittest.main()
