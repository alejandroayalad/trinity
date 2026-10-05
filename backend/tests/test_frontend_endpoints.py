"""Check synthetic national values and schedule rules without external services."""
from datetime import datetime, timezone
import unittest

from trinity.dashboard.service import NationalService, dashboard_from_preview, metric_value, parse_national
from trinity.errors import Problem
from trinity.settings.commands import SettingsInput, next_check
from trinity.queries.preview import ResolvedPreview
from test_preview_unit import page, publication


class NationalTests(unittest.TestCase):
    def test_exact_share_missing_zero_and_out_of_range(self):
        """Half-up ties and signed observations must survive the display calculation."""
        self.assertEqual(metric_value('1.005', '100')['value'], '1.01')
        self.assertEqual(metric_value('-1.005', '100')['value'], '-1.01')
        self.assertEqual(metric_value('0', '100')['value'], '0.00')
        self.assertEqual(metric_value('200', '100')['value'], '200.00')
        self.assertEqual(metric_value('5', '0')['reason'], 'zero_capacity')
        self.assertEqual(metric_value(None, None)['reason'], 'not_reported')

    def test_closed_grammar_and_semantic_bounds(self):
        service = NationalService(None, None)
        for pairs in ([('preset', 'bad')], [('start', '2026-02-30')], [('preset', '30d'), ('preset', '90d')], [('extra', '1')]):
            with self.subTest(pairs=pairs), self.assertRaises(Problem):
                parse_national(pairs)
        for pairs in ([('start', '2026-01-01')], [('preset', '30d'), ('start', '2026-01-01'), ('end', '2026-01-02')], [('start', '2026-01-02'), ('end', '2026-01-01')]):
            with self.subTest(pairs=pairs), self.assertRaises(Problem):
                service.validate_input('national', parse_national(pairs))
        latest = publication().latest_observation_date
        resolved = service.resolve_input('national', parse_national([('preset', '1y')]), latest)
        self.assertEqual((resolved.end - resolved.start).days, 364)

    def test_gaps_and_summary_are_calendar_points_not_zero_rows(self):
        latest = publication().latest_observation_date
        result = dashboard_from_preview(page(ResolvedPreview('national', latest, latest), rows=[]), None)
        self.assertEqual(result['summary'], result['days'][-1])


class ScheduleTests(unittest.TestCase):
    def test_closed_settings_input(self):
        for value in ({'schedule_enabled': 'true', 'daily_time': '06:00', 'timezone': 'UTC'},
                      {'schedule_enabled': True, 'daily_time': '24:00', 'timezone': 'UTC'},
                      {'schedule_enabled': True, 'daily_time': '06:00', 'timezone': 'invalid/zone'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SettingsInput.model_validate(value)

    def test_dst_gap_is_skipped_and_fold_uses_first_occurrence(self):
        """New York loses 02:30 in March and repeats 01:30 in November."""
        first, _ = next_check(datetime(2026, 3, 8, 0, tzinfo=timezone.utc), '02:30', 'America/New_York')
        self.assertEqual(first, datetime(2026, 3, 9, 6, 30, tzinfo=timezone.utc))
        first, _ = next_check(datetime(2026, 11, 1, 0, tzinfo=timezone.utc), '01:30', 'America/New_York')
        self.assertEqual(first, datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc))
        after, _ = next_check(first, '01:30', 'America/New_York')
        self.assertEqual(after, datetime(2026, 11, 2, 6, 30, tzinfo=timezone.utc))


class ChoiceEngineTests(unittest.TestCase):
    def test_distinct_latest_name_literal_search_and_signed_pagination(self):
        """Use real DataFusion so search is tested as a literal, including wildcard text."""
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from dataclasses import replace
        from datetime import date
        from sql_fixture import write_table
        from test_preview_unit import codec
        from trinity.contracts.queries import ChoiceOperation, request_message, read_request, canonical_message
        from trinity.queries.runtime.choices import execute_choices
        from trinity.queries.choices import ChoiceCodec, build_choice_response
        from uuid import uuid4
        public = publication()
        operation = ChoiceOperation('facility', str(public.publication_event_id), str(public.version_id),
                                    '2025-01-01', '2025-01-03', page_size=1)
        self.assertEqual(read_request(canonical_message(request_message(uuid4(), public.version_id, operation)))[1], operation)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            write_table(root, 'facility', count=4, values=[
                {'facility': '01', 'facilityName': 'Old', 'period': date(2025, 1, 1)},
                {'facility': '01', 'facilityName': 'New%_Name', 'period': date(2025, 1, 2)},
                {'facility': '01', 'facilityName': None, 'period': date(2025, 1, 3)},
                {'facility': '1', 'facilityName': None, 'period': date(2025, 1, 1)}])
            batch = execute_choices(operation, root)
            self.assertEqual(batch, {'items': [{'facility': '01', 'facilityName': 'New%_Name'}], 'has_more': True})
            signer = ChoiceCodec(codec().keys, 'facilities')
            response = build_choice_response(operation, public, batch, signer)
            next_operation = signer.decode(response.next_cursor)
            self.assertEqual(execute_choices(next_operation, root)['items'], [{'facility': '1', 'facilityName': None}])
            self.assertEqual(execute_choices(replace(operation, search='%_'), root)['items'], batch['items'])
            self.assertEqual(execute_choices(replace(operation, search='NEW%_'), root)['items'], batch['items'])
            self.assertEqual(execute_choices(replace(operation, search="' OR TRUE --"), root)['items'], [])
            with self.assertRaises(Problem):
                signer.decode(response.next_cursor[:-1] + ('A' if response.next_cursor[-1] != 'A' else 'B'))

    def test_generator_choices_keep_exact_parent_and_ids(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from sql_fixture import write_table
        from trinity.contracts.queries import ChoiceOperation
        from trinity.queries.runtime.choices import execute_choices
        public = publication()
        operation = ChoiceOperation('generator', str(public.publication_event_id), str(public.version_id),
                                    '2025-01-01', '2025-01-03', facility='01', selection='generators')
        with TemporaryDirectory() as temp:
            root = Path(temp)
            write_table(root, 'generator', values=[{'facility': '01', 'generator': '01'},
                {'facility': '01', 'generator': '1'}, {'facility': '1', 'generator': '01'}])
            self.assertEqual(execute_choices(operation, root)['items'], [
                {'facility': '01', 'generator': '01'}, {'facility': '01', 'generator': '1'}])
