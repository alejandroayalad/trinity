"""Exercise full-range choice reduction, strict input and bound bookmarks."""

from dataclasses import replace
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from trinity.contracts.choices import ChoiceOperation
from trinity.contracts.queries import canonical_message, request_message
from trinity.errors import Problem
from trinity.queries.choice_schemas import build_choice_response
from trinity.queries.choices import ChoiceCursorCodec, parse_choice_input
from trinity.queries.runtime.choices import execute_choices
from trinity.queries.runtime.__main__ import run_request
from sql_fixture import write_table
from test_preview_unit import codec, publication


def choice_codec():
    return ChoiceCursorCodec(codec().keys)


def operation(**changes):
    values = dict(dataset='generator', publication_event_id=str(publication().publication_event_id),
                  version_id=str(publication().version_id), start='2025-01-01', end='2025-01-03')
    return ChoiceOperation(**(values | changes))


class ChoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, rows, dataset='generator'):
        write_table(self.root, dataset, count=len(rows), values=rows)

    def test_latest_non_null_name_and_same_date_binary_tie_before_search(self):
        # The null on the latest date must not erase the last known label.
        # Multiple units can report conflicting names for one Plant on one day.
        self.write([
            {'period': date(2025,1,1), 'facility': '0046', 'facilityName': 'Old', 'generator': '1'},
            {'period': date(2025,1,2), 'facility': '0046', 'facilityName': 'Zulu', 'generator': '1'},
            {'period': date(2025,1,2), 'facility': '0046', 'facilityName': 'Alpha', 'generator': '2'},
            {'period': date(2025,1,3), 'facility': '0046', 'facilityName': None, 'generator': '1'},
            {'period': date(2025,1,3), 'facility': '46', 'facilityName': None, 'generator': '1'},
        ])
        result = execute_choices(operation(), self.root)
        self.assertEqual(result, {'items': [{'facility':'0046','facilityName':'Alpha'},
                                           {'facility':'46','facilityName':None}], 'has_more':False})
        self.assertEqual(execute_choices(operation(search='OLD'), self.root)['items'], [])
        self.assertEqual(execute_choices(operation(search='alpHA'), self.root)['items'], result['items'][:1])
        self.assertEqual(execute_choices(operation(end='2025-01-01'), self.root)['items'][0]['facilityName'], 'Old')

    def test_distinct_over_more_than_preview_limit_and_binary_paging(self):
        rows = [{'period':date(2025,1,1), 'facility':'01', 'generator':str(i), 'facilityName':'Plant'}
                for i in range(1100)]
        ids = ['1','A','a','é','😀']
        rows += [{'period':date(2025,1,2), 'facility':f, 'generator':'1'} for f in ids]
        self.write(rows)
        op = operation(page_size=1)
        found = []
        while True:
            result = execute_choices(op, self.root)
            page = build_choice_response(op, publication(), result, codec=choice_codec())
            found.extend(item.facility for item in page.items)
            if page.next_cursor is None:
                break
            op = choice_codec().decode(page.next_cursor)
        self.assertEqual(found, ['01', *ids])
        self.assertEqual(len(found), len(set(found)))

    def test_generators_are_distinct_and_scoped_to_exact_parent(self):
        self.write([{'period':date(2025,1,1), 'facility':'0046', 'generator':'01'},
                    {'period':date(2025,1,2), 'facility':'0046', 'generator':'01'},
                    {'period':date(2025,1,2), 'facility':'0046', 'generator':'1'},
                    {'period':date(2025,1,1), 'facility':'46', 'generator':'2'}])
        op = operation(choice='generators', facility='0046', page_size=1)
        first = execute_choices(op, self.root)
        self.assertEqual(first, {'items':[{'facility':'0046','generator':'01'}], 'has_more':True})
        second = execute_choices(replace(op, after='01'), self.root)
        self.assertEqual(second, {'items':[{'facility':'0046','generator':'1'}], 'has_more':False})
        self.assertEqual(execute_choices(replace(op, facility='missing'), self.root)['items'], [])

    def test_literal_search_unicode_casefold_and_injection_text(self):
        names = ['100%_Plant', 'Straße', "x' OR TRUE --", 'Other']
        self.write([{'period':date(2025,1,1), 'facility':str(i), 'facilityName':name}
                    for i, name in enumerate(names)])
        for search, expected in [('%_', '0'), ('STRASSE', '1'), ("x' OR TRUE --", '2'), ('0','0')]:
            with self.subTest(search=search):
                self.assertEqual([x['facility'] for x in execute_choices(operation(search=search),self.root)['items']], [expected])

    def test_facility_dataset_and_empty_range(self):
        self.write([{'facility':'01','facilityName':'Plant'}], 'facility')
        op = operation(dataset='facility')
        self.assertEqual(execute_choices(op,self.root)['items'][0]['facility'], '01')
        empty = execute_choices(replace(op,start='2025-01-03'), self.root)
        response = build_choice_response(op,publication(),empty,codec=choice_codec())
        self.assertEqual(response.items, [])
        self.assertIsNone(response.next_cursor)

    def test_primitive_inputs_reject_duplicates_unknowns_and_wrong_route_parameters(self):
        for choice, pairs in [
            ('facilities',[('search','a'),('search','b')]), ('facilities',[('facility','01')]),
            ('generators',[('search','x')]), ('generators',[('generator','1')]),
            ('facilities',[('limit','101')]), ('facilities',[('limit','01')]),
            ('facilities',[('search','x'*101)]), ('facilities',[('search',' ')]),
            ('facilities',[('end','2025-02-29')]), ('facilities',[('end','2025-01-01T00:00:00')])]:
            with self.subTest(pairs=pairs), self.assertRaises(Problem):
                parse_choice_input(pairs,choice)
        with self.assertRaises(Problem):
            parse_choice_input([], 'facilities', body=b'{}')
        request = parse_choice_input([('search',' Plant ')],'facilities')
        self.assertEqual(request.preview.limit,50)
        self.assertEqual(request.search,' Plant ')

    def test_bookmark_tamper_preview_separation_and_bound_operation_fields(self):
        op = operation(search='Alpha', page_size=1)
        token = choice_codec().encode(op,'01')
        self.assertEqual(choice_codec().decode(token), replace(op,after='01'))
        for bad in (token+'x', 'pv1'+token[3:], token[:-10]+'AAAAAAAAAA'):
            with self.assertRaises(Problem):
                choice_codec().decode(bad)
        with self.assertRaises(Problem):
            codec().decode(token)
        for changes in ({'choice':'generators'}, {'dataset':'national'}, {'page_size':101},
                        {'page_size':True}, {'start':'2024-01-01'}, {'protocol_version':True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(op,**changes)

    def test_runtime_dispatch_binding_and_reject_cross_kind(self):
        self.write([{'facility':'01','facilityName':'Plant'}])
        op = operation()
        message = request_message(uuid4(),op.version_id,op)
        self.assertEqual(run_request(canonical_message(message),self.root)['result']['items'][0]['facility'],'01')
        for bad in (dict(message,operation_kind='preview'), dict(message,operation_digest='0'*64),
                    dict(message,version_id=str(uuid4()))):
            with patch('trinity.queries.runtime.__main__.execute_choices') as execute:
                with self.assertRaises(ValueError):
                    run_request(canonical_message(bad),self.root)
                execute.assert_not_called()

    def test_bad_runtime_page_fails_instead_of_silently_repairing(self):
        op = operation(page_size=2)
        a, b = {'facility':'01','facilityName':'A'}, {'facility':'02','facilityName':'B'}
        for batch in ({'items':[b,a],'has_more':False}, {'items':[a,a],'has_more':False},
                      {'items':[a],'has_more':True}, {'items':[a],'has_more':1},
                      {'items':[dict(a,hidden='x')],'has_more':False}):
            with self.subTest(batch=batch), self.assertRaises(Problem):
                build_choice_response(op,publication(),batch,codec=choice_codec())
        with self.assertRaises(Problem):
            build_choice_response(operation(choice='generators',facility='01'),publication(),
                {'items':[{'facility':'02','generator':'1'}],'has_more':False},codec=choice_codec())
        with self.assertRaises(Problem):
            build_choice_response(operation(search='missing'),publication(),
                {'items':[a],'has_more':False},codec=choice_codec())

    def test_maximum_unicode_bookmarks_fit_public_limit(self):
        for op in (operation(search='😀'*100), operation(choice='generators',facility='😀'*128)):
            token = choice_codec().encode(op,'😀'*128)
            self.assertLessEqual(len(token),4096)
            self.assertEqual(choice_codec().decode(token),replace(op,after='😀'*128))

    def test_runtime_output_size_failure_has_no_partial_page(self):
        from trinity.queries.runtime.engine import QueryExecutionError
        self.write([{'facility':'01','facilityName':'x'*(5*1024*1024)}])
        with self.assertRaises(QueryExecutionError) as caught:
            execute_choices(operation(),self.root)
        self.assertEqual(caught.exception.code,'query_resource_limit')
