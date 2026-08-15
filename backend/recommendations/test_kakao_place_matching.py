from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from recommendations.models import (
    KakaoPlaceMatch,
    KakaoPlaceSearchCache,
    Place,
    SourcePlaceRecord,
)
from recommendations.services.kakao_place_matcher import (
    choose_match,
    normalize_address,
    normalize_name,
)


def kakao_candidate(
    *,
    place_id="12345",
    name="스타벅스 강남역점",
    road_address="서울 강남구 강남대로 390",
    address="서울 강남구 역삼동 825",
    lat="37.4979",
    lng="127.0276",
    phone="02-1234-5678",
    category_group_code="CE7",
):
    return {
        "id": place_id,
        "place_name": name,
        "road_address_name": road_address,
        "address_name": address,
        "y": lat,
        "x": lng,
        "phone": phone,
        "category_group_code": category_group_code,
        "category_name": "음식점 > 카페",
        "place_url": f"https://place.map.kakao.com/{place_id}",
    }


class KakaoPlaceMatcherTests(TestCase):
    def make_record(self, **overrides):
        values = {
            "source": "localdata",
            "dataset": "rest_restaurant",
            "source_record_id": "LOCAL-1",
            "name": "스타벅스 강남역점",
            "category": "cafe",
            "address": "서울 강남구 역삼동 825",
            "road_address": "서울특별시 강남구 강남대로 390",
            "sido_name": "서울특별시",
            "sigungu_name": "강남구",
            "source_x": "127.02758",
            "source_y": "37.49792",
            "coordinate_reference_system": "EPSG:4326",
            "raw": {"SITE_TEL": "02-1234-5678"},
        }
        values.update(overrides)
        return SourcePlaceRecord.objects.create(**values)

    def test_normalizes_company_noise_but_preserves_branch_identity(self):
        self.assertEqual(normalize_name("(주) 스타벅스 강남역점"), "스타벅스강남역점")
        self.assertEqual(
            normalize_address("(06232) 서울특별시 강남구 강남대로 390"),
            "서울특별시강남구강남대로390",
        )

    def test_confirms_strong_name_address_coordinate_and_phone_match(self):
        record = self.make_record()
        outcome = choose_match(
            record,
            [kakao_candidate()],
            source_coordinates=(37.49792, 127.02758),
        )
        self.assertEqual(outcome["status"], "confirmed")
        self.assertGreaterEqual(outcome["top"]["score"], 90)

    def test_keeps_close_top_candidates_ambiguous(self):
        record = self.make_record()
        outcome = choose_match(
            record,
            [
                kakao_candidate(place_id="1"),
                kakao_candidate(place_id="2", lat="37.49791", lng="127.02759"),
            ],
            source_coordinates=(37.49792, 127.02758),
        )
        self.assertEqual(outcome["status"], "ambiguous")
        self.assertLess(outcome["margin"], 12)

    def test_branch_conflict_cannot_auto_confirm(self):
        record = self.make_record()
        candidate = kakao_candidate(name="스타벅스 역삼점")
        outcome = choose_match(
            record,
            [candidate],
            source_coordinates=(37.49792, 127.02758),
        )
        self.assertNotEqual(outcome["status"], "confirmed")
        self.assertTrue(outcome["top"]["details"]["branch_conflict"])


class KakaoPlaceMatchingCommandTests(TestCase):
    def make_record(self, source_record_id="LOCAL-1"):
        return SourcePlaceRecord.objects.create(
            source="localdata",
            dataset="rest_restaurant",
            source_record_id=source_record_id,
            name="스타벅스 강남역점",
            category="cafe",
            address="서울 강남구 역삼동 825",
            road_address="서울특별시 강남구 강남대로 390",
            sido_name="서울특별시",
            sigungu_name="강남구",
            source_x="127.02758",
            source_y="37.49792",
            coordinate_reference_system="EPSG:4326",
            raw={"SITE_TEL": "02-1234-5678"},
        )

    @patch(
        "recommendations.management.commands.match_source_places_to_kakao.search_places_by_keyword"
    )
    def test_confirmed_match_creates_kakao_canonical_place_and_reuses_cache(self, mock_search):
        record = self.make_record()
        mock_search.return_value = {"documents": [kakao_candidate()]}

        output = StringIO()
        call_command(
            "match_source_places_to_kakao",
            source="localdata",
            limit=1,
            stdout=output,
        )

        record.refresh_from_db()
        match = KakaoPlaceMatch.objects.get(source_record=record)
        self.assertEqual(match.status, "confirmed")
        self.assertEqual(match.kakao_place_id, "12345")
        self.assertEqual(record.normalized_place.source, "kakao_local")
        self.assertEqual(record.normalized_place.external_id, "12345")
        self.assertEqual(Place.objects.filter(source="kakao_local").count(), 1)
        self.assertEqual(KakaoPlaceSearchCache.objects.count(), 1)
        self.assertEqual(mock_search.call_count, 1)

        call_command(
            "match_source_places_to_kakao",
            source="localdata",
            limit=1,
            refresh=True,
            stdout=StringIO(),
        )
        self.assertEqual(mock_search.call_count, 1)
        match.refresh_from_db()
        self.assertEqual(match.attempt_count, 2)

    @patch(
        "recommendations.management.commands.match_source_places_to_kakao.search_places_by_keyword"
    )
    def test_low_score_match_is_saved_unmatched_without_linking(self, mock_search):
        record = self.make_record()
        mock_search.return_value = {
            "documents": [
                kakao_candidate(
                    place_id="999",
                    name="전혀 다른 식당",
                    road_address="부산 해운대구 해운대로 1",
                    address="부산 해운대구 우동 1",
                    lat="35.1631",
                    lng="129.1635",
                    phone="051-000-0000",
                    category_group_code="FD6",
                )
            ]
        }

        call_command(
            "match_source_places_to_kakao",
            source="localdata",
            limit=1,
            stdout=StringIO(),
        )

        record.refresh_from_db()
        match = KakaoPlaceMatch.objects.get(source_record=record)
        self.assertEqual(match.status, "unmatched")
        self.assertIsNone(record.normalized_place)
        self.assertFalse(Place.objects.filter(source="kakao_local", external_id="999").exists())

    @patch(
        "recommendations.management.commands.match_source_places_to_kakao.search_places_by_keyword"
    )
    def test_weak_refresh_never_revokes_an_existing_confirmed_match(self, mock_search):
        record = self.make_record()
        canonical = Place.objects.create(
            name=record.name,
            category="cafe",
            address=record.road_address,
            lat=37.49792,
            lng=127.02758,
            source="kakao_local",
            external_id="already-confirmed",
        )
        record.normalized_place = canonical
        record.save(update_fields=["normalized_place"])
        KakaoPlaceMatch.objects.create(
            source_record=record,
            status="confirmed",
            canonical_place=canonical,
            kakao_place_id=canonical.external_id,
            score=95,
        )
        mock_search.return_value = {"documents": []}

        call_command(
            "match_source_places_to_kakao",
            source="localdata",
            refresh=True,
            refresh_cache=True,
            limit=1,
            stdout=StringIO(),
        )

        record.refresh_from_db()
        match = KakaoPlaceMatch.objects.get(source_record=record)
        self.assertEqual(match.status, "confirmed")
        self.assertEqual(match.kakao_place_id, "already-confirmed")
        self.assertEqual(record.normalized_place_id, canonical.id)
        self.assertTrue(match.score_details["confirmed_match_preserved"])

    @patch(
        "recommendations.management.commands.match_source_places_to_kakao.search_places_by_keyword"
    )
    def test_after_id_and_api_quota_make_batch_resumable(self, mock_search):
        first = self.make_record("LOCAL-1")
        second = self.make_record("LOCAL-2")
        mock_search.return_value = {"documents": []}

        output = StringIO()
        call_command(
            "match_source_places_to_kakao",
            source="localdata",
            after_id=first.id,
            max_api_requests=1,
            max_queries=2,
            stdout=output,
        )

        self.assertFalse(KakaoPlaceMatch.objects.filter(source_record=first).exists())
        self.assertFalse(KakaoPlaceMatch.objects.filter(source_record=second).exists())
        self.assertIn("quota_reached=True", output.getvalue())
        self.assertIn(f"last_id={first.id}", output.getvalue())
