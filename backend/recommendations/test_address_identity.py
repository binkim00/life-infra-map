"""Frozen end-to-end acceptance cases for the pure address identity parser."""
import json
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from recommendations.models import Place, PlaceTagEvidence, Tag
from recommendations.services.automatic_content_review import assess_content
from recommendations.services.address_details import FieldState
from recommendations.services.address_identity import parse_address_details


class FrozenAddressIdentityTests(SimpleTestCase):
    def test_all_normal_and_adversarial_cases(self):
        corpus = json.loads((Path(__file__).parent / 'fixtures' / 'address_identity_acceptance.json').read_text(encoding='utf-8'))
        self.assertEqual(len(corpus['cases']), 356)
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            for case in corpus['cases']:
                with self.subTest(case=case['case']):
                    name = case['registered_name']
                    row = PlaceTagEvidence(
                        place=Place(name=name, address=case['address'], category='cafe', source='test', lat=35.1, lng=129.1),
                        tag=Tag(name='콘센트있음'), source='web_search', polarity='positive',
                        source_reference='https://example.com/article', evidence=case['quote'],
                        context={'source_title': case['title'] or f'{name} 후기'},
                    )
                    self.assertEqual(assess_content(row)[0], case['expected'])


class StructuredAddressDetailsTests(SimpleTestCase):
    def test_missing_parsed_and_unresolved_states_are_distinct(self):
        self.assertEqual(parse_address_details('').state('층'), FieldState.MISSING)
        known = parse_address_details('1층의101호실')
        self.assertTrue(known.complete)
        self.assertEqual(known.state('층'), FieldState.PARSED)
        self.assertEqual(known.state('관'), FieldState.MISSING)
        unknown = parse_address_details('1층 층수는확인불가')
        self.assertFalse(unknown.complete)
        self.assertEqual(unknown.state('층'), FieldState.UNRESOLVED)
        self.assertIn((False, '1'), unknown.as_units()['층'])
        self.assertIsNone(unknown.as_units()['unparsed'])
        self.assertEqual(next(t.field_name for t in unknown.tokens if t.kind == 'field'), '층')

    def test_tokens_retain_spans_across_particles_and_equivalent_units(self):
        text = '1f의제0101호실'
        parsed = parse_address_details(text)
        self.assertTrue(parsed.complete)
        self.assertEqual(parsed.as_units(), {'층': {(False, '1')}, '호': {(False, '101')}})
        for token in parsed.tokens:
            self.assertEqual(text[token.start:token.end], token.text)

    def test_unresolved_ranges_retain_a_reason_and_source_span(self):
        for text in ('2층-미상', '2층~미상', '2층부터미상', '2층내지미기재', 'B1~B2'.lower()):
            with self.subTest(text=text):
                parsed = parse_address_details(text)
                self.assertFalse(parsed.complete)
                self.assertEqual(parsed.issues[0].reason, 'unresolved_range')
                issue = parsed.issues[0]
                self.assertEqual(text[issue.start:issue.end], issue.text)

    def test_unknown_attached_suffix_is_not_ordinary_prose(self):
        for text in ('1층점', '1층지하점', '1층제2지점', '101호실점'):
            with self.subTest(text=text):
                parsed = parse_address_details(text)
                self.assertFalse(parsed.complete)
                self.assertEqual(parsed.issues[0].reason, 'unrecognized_attached_suffix')

    def test_conjunction_keeps_both_room_numbers(self):
        self.assertEqual(parse_address_details('1층101호실과102호실').as_units()['호'], {(False, '101'), (False, '102')})

    def test_facility_prose_cannot_verify_the_store_floor(self):
        parsed = parse_address_details('1층 화장실은2층에 있어요')
        self.assertTrue(parsed.complete)
        self.assertEqual(parsed.as_units()['층'], {(False, '1')})
        self.assertTrue(parsed.remainder.startswith('화장실'))
        self.assertEqual(parsed.stop_reason, 'facility_prose')

    def test_unknown_room_and_floor_fields_do_not_depend_on_spacing(self):
        for field in ('층수', '호수'):
            for value in ('미확정', '확인불가', '부정확', '미상', '정보없음', '알 수 없음', '101', '제101', ''):
                for gap in ('', ' '):
                    with self.subTest(field=field, value=value, gap=gap):
                        self.assertFalse(parse_address_details(f'1층101호 {field}는{gap}{value}').complete)

    def test_equivalent_spacing_and_particles_have_the_same_final_decision(self):
        base, name = '부산 중구 중앙대로 100', '테스트커피 서면점'
        for particle in ('의', '과', '와'):
            for gap in ('', ' '):
                for room in ('101호', '101호실', '제0101호실'):
                    for conflict in (False, True):
                        for in_title in (True, False):
                            detail = f'1층{particle}{gap}' + (room.replace('101', '102') if conflict else room)
                            quote = f'{base} 1층 101호 {name}에는 콘센트가 있어요.' if in_title else f'{base} {detail} {name}에는 콘센트가 있어요.'
                            row = PlaceTagEvidence(
                                place=Place(name=name, address=f'{base} 1층 101호', category='cafe', source='test', lat=35.1, lng=129.1),
                                tag=Tag(name='콘센트있음'), source='web_search', polarity='positive',
                                source_reference='https://example.com/article', evidence=quote,
                                context={'source_title': f'{name} {detail} 후기' if in_title else f'{name} 후기'},
                            )
                            with self.subTest(detail=detail, in_title=in_title):
                                self.assertEqual(assess_content(row)[0], 'hold' if conflict else 'approve')
