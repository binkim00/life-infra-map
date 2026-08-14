from django.test import TestCase

from recommendations.management.commands.sync_tourapi_tag_details import parse_tourapi_item, sync_tourapi_details
from recommendations.models import Place, PlaceTag


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return FakeResponse(self.payload)


class TourApiTagDetailTests(TestCase):
    def test_parses_single_item_shape(self):
        item = parse_tourapi_item({
            'response': {'header': {'resultCode': '00'}, 'body': {
                'items': {'item': {'parkingfood': '주차 가능'}},
            }},
        })
        self.assertEqual(item['parkingfood'], '주차 가능')

    def test_enriches_place_and_generates_meaningful_tags(self):
        place = Place.objects.create(
            name='전국 상세 식당', category='restaurant',
            address='서울특별시 종로구', lat=37.5, lng=127.0,
            source='tour_api', external_id='tourism_39_99',
            raw={'raw': {'contentid': '99', 'contenttypeid': '39'}},
        )
        session = FakeSession({
            'response': {'header': {'resultCode': '00'}, 'body': {
                'items': {'item': [{
                    'parkingfood': '건물 주차장 이용 가능',
                    'packing': '가능',
                    'kidsfacility': '없음',
                }]},
            }},
        })
        stats = sync_tourapi_details([place], service_key='test', session=session)
        place.refresh_from_db()
        self.assertEqual(stats['updated'], 1)
        self.assertEqual(stats['tag_matches'], 2)
        self.assertIn('tourapi_intro', place.raw['tag_evidence_sources'])
        self.assertEqual(
            set(PlaceTag.objects.values_list('tag__name', flat=True)),
            {'주차가능', '포장가능'},
        )
        self.assertEqual(session.calls[0][1]['contentId'], '99')
