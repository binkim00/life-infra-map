import csv
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from pyproj import Transformer

from recommendations.management.commands.generate_objective_place_tags import generate_tags
from recommendations.management.commands.import_localdata_records import (
    import_localdata_csv,
)
from recommendations.management.commands.promote_source_places import promote_records
from recommendations.management.commands.sync_localdata_api import (
    normalize_service_key,
    parse_api_response,
    sync_localdata_api,
)
from recommendations.services.data_source_manifest import get_dataset_config
from recommendations.models import (
    DataSourceSyncRun,
    Place,
    PlaceCoverage,
    PlaceTag,
    PlaceTagEvidence,
    SourcePlaceRecord,
    Tag,
)


class LocaldataImportTests(TestCase):
    def write_csv(self, rows):
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            suffix=".csv",
            delete=False,
        )
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        with handle:
            fieldnames = list(dict.fromkeys(key for row in rows for key in row))
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return Path(handle.name)

    def sample_rows(self):
        return [
            {
                "관리번호": "A-1",
                "사업장명": "전국 브런치 카페",
                "업태구분명": "커피숍",
                "상세영업상태명": "영업",
                "영업상태구분코드": "01",
                "소재지전체주소": "부산광역시 부산진구 부전동 1",
                "도로명전체주소": "부산광역시 부산진구 중앙대로 1",
                "개방자치단체코드": "3290000",
                "좌표정보(x)": "386000",
                "좌표정보(y)": "286000",
                "인허가일자": "20260102",
                "최종수정시점": "20260814112233",
            },
            {
                "관리번호": "A-2",
                "사업장명": "폐업 식당",
                "업태구분명": "한식",
                "상세영업상태명": "폐업",
                "영업상태구분코드": "03",
                "소재지전체주소": "강원특별자치도 강릉시 포남동 1",
                "도로명전체주소": "강원특별자치도 강릉시 경강로 1",
                "개방자치단체코드": "4200000",
                "좌표정보(x)": "420000",
                "좌표정보(y)": "340000",
                "인허가일자": "20200102",
                "폐업일자": "20260801",
                "최종수정시점": "20260802112233",
            },
        ]

    def test_imports_nationwide_rows_into_staging_and_tracks_sync(self):
        path = self.write_csv(self.sample_rows())

        stats = import_localdata_csv(
            path=path,
            source="localdata",
            dataset="general_restaurant",
            default_category="restaurant",
        )

        self.assertEqual(stats, {
            "read": 2,
            "valid": 2,
            "created": 2,
            "updated": 0,
            "skipped": 0,
            "duplicates": 0,
        })
        cafe = SourcePlaceRecord.objects.get(source_record_id="A-1")
        self.assertEqual(cafe.category, "cafe")
        self.assertEqual(cafe.sido_name, "부산광역시")
        self.assertEqual(cafe.sigungu_name, "부산진구")
        self.assertTrue(cafe.is_active)
        self.assertEqual(cafe.coordinate_reference_system, "EPSG:5174")

        closed = SourcePlaceRecord.objects.get(source_record_id="A-2")
        self.assertFalse(closed.is_active)
        self.assertEqual(closed.sido_name, "강원특별자치도")

        sync = DataSourceSyncRun.objects.get()
        self.assertEqual(sync.status, "succeeded")
        self.assertEqual(sync.stats["created"], 2)
        self.assertEqual(len(sync.source_checksum), 64)

    def test_reimport_updates_existing_records(self):
        rows = self.sample_rows()
        path = self.write_csv(rows)
        kwargs = {
            "path": path,
            "source": "localdata",
            "dataset": "general_restaurant",
            "default_category": "restaurant",
        }
        import_localdata_csv(**kwargs)
        rows[0]["사업장명"] = "전국 브런치 카페 새이름"
        path = self.write_csv(rows)
        stats = import_localdata_csv(**{**kwargs, "path": path, "sync_type": "delta"})

        self.assertEqual(stats["created"], 0)
        self.assertEqual(stats["updated"], 2)
        self.assertEqual(
            SourcePlaceRecord.objects.get(source_record_id="A-1").name,
            "전국 브런치 카페 새이름",
        )

    def test_dry_run_does_not_write_database(self):
        path = self.write_csv(self.sample_rows())
        stats = import_localdata_csv(
            path=path,
            source="localdata",
            dataset="general_restaurant",
            default_category="restaurant",
            dry_run=True,
        )

        self.assertEqual(stats["valid"], 2)
        self.assertFalse(SourcePlaceRecord.objects.exists())
        self.assertFalse(DataSourceSyncRun.objects.exists())


class PlaceCoverageTests(TestCase):
    def test_rebuilds_coverage_from_normalized_places_and_evidence(self):
        place = Place.objects.create(
            name="전국 테스트 카페",
            category="cafe",
            address="부산광역시 부산진구",
            lat=35.15,
            lng=129.05,
            source="localdata",
            external_id="coverage-place-1",
        )
        record = SourcePlaceRecord.objects.create(
            source="localdata",
            dataset="rest_restaurant",
            source_record_id="coverage-record-1",
            name=place.name,
            category="cafe",
            business_status="영업",
            is_active=True,
            address=place.address,
            sido_name="부산광역시",
            sigungu_name="부산진구",
            administrative_code="3290000",
            normalized_place=place,
        )
        tag = Tag.objects.create(name="조용함", tag_type="recommendation")
        PlaceTag.objects.create(
            place=place,
            tag=tag,
            source="user_verified",
            status="confirmed",
            confidence=90,
        )
        PlaceTagEvidence.objects.create(
            place=place,
            tag=tag,
            source="user_verified",
            polarity="positive",
            confidence=90,
            evidence="방문 후 확인",
        )

        call_command("rebuild_place_coverage", source="localdata")

        coverage = PlaceCoverage.objects.get(
            administrative_code=record.administrative_code,
            category="cafe",
            source="localdata",
        )
        self.assertEqual(coverage.source_record_count, 1)
        self.assertEqual(coverage.normalized_place_count, 1)
        self.assertEqual(coverage.tagged_place_count, 1)
        self.assertEqual(coverage.evidence_place_count, 1)
        self.assertEqual(coverage.coverage_score, 100)


class LocaldataApiSyncTests(TestCase):
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
            self.calls.append({"url": url, "params": params, "timeout": timeout})
            return LocaldataApiSyncTests.FakeResponse(self.payload)

    def test_parses_standard_data_go_kr_response(self):
        items, total = parse_api_response({
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
                "body": {
                    "items": {"item": [{"mgtNo": "A-1"}]},
                    "totalCount": "1",
                },
            }
        })
        self.assertEqual(items, [{"mgtNo": "A-1"}])
        self.assertEqual(total, 1)

    def test_normalizes_encoded_data_go_kr_service_key(self):
        self.assertEqual(normalize_service_key("abc%2Bdef%3D%3D"), "abc+def==")
        self.assertEqual(normalize_service_key("abc+def=="), "abc+def==")

    def test_manifest_uses_dataset_specific_service_keys(self):
        _, rest_config = get_dataset_config("localdata", "rest_restaurant")
        _, bakery_config = get_dataset_config("localdata", "bakery")

        self.assertEqual(
            rest_config["service_key_environment_variable"],
            "DATA_GO_KR_REST_RESTAURANT_SERVICE_KEY",
        )
        self.assertEqual(
            bakery_config["service_key_environment_variable"],
            "DATA_GO_KR_BAKERY_SERVICE_KEY",
        )

    def test_syncs_current_uppercase_localdata_api_fields(self):
        payload = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": [{
                        "MNG_NO": "UPPER-API-1",
                        "BPLC_NM": "Nationwide Cafe",
                        "BZSTAT_SE_NM": "Cafe",
                        "DTL_SALS_STTS_NM": "Open",
                        "SALS_STTS_CD": "01",
                        "LOTNO_ADDR": "Seoul Jongno-gu 1",
                        "ROAD_NM_ADDR": "Seoul Jongno-gu Test-ro 1",
                        "OPN_ATMY_GRP_CD": "3000000",
                        "CRD_INFO_X": "200000",
                        "CRD_INFO_Y": "450000",
                        "LCPMT_YMD": "20260101",
                        "LAST_MDFCN_PNT": "20260814010101",
                    }],
                    "totalCount": 1,
                },
            }
        }
        stats = sync_localdata_api(
            dataset="general_restaurant",
            dataset_config={
                "api_url": "https://example.test/general_restaurants/info",
                "category": "restaurant",
            },
            service_key="test-key",
            session=self.FakeSession(payload),
        )

        self.assertEqual(stats["created"], 1)
        record = SourcePlaceRecord.objects.get(source_record_id="UPPER-API-1")
        self.assertEqual(record.name, "Nationwide Cafe")
        self.assertEqual(record.administrative_code, "3000000")

    def test_uses_actual_response_size_when_deciding_last_page(self):
        payload = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": {"item": [{
                        "MNG_NO": "PAGE-SIZE-1",
                        "BPLC_NM": "Page Size Place",
                        "LOTNO_ADDR": "Seoul Jongno-gu 1",
                    }]},
                    "totalCount": 1000,
                },
            }
        }
        stats = sync_localdata_api(
            dataset="general_restaurant",
            dataset_config={
                "api_url": "https://example.test/general_restaurants/info",
                "category": "restaurant",
            },
            service_key="test-key",
            page_size=1000,
            max_pages=2,
            dry_run=True,
            session=self.FakeSession(payload),
        )

        self.assertEqual(stats["pages"], 2)
        self.assertEqual(stats["read"], 2)

    def test_syncs_api_rows_using_manifest_field_names(self):
        payload = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": {
                        "item": [{
                            "mgtNo": "API-1",
                            "bplcNm": "전국 API 카페",
                            "uptaeNm": "커피숍",
                            "dtlStateNm": "영업",
                            "trdStateGbn": "01",
                            "siteWhlAddr": "대전광역시 유성구 봉명동 1",
                            "rdnWhlAddr": "대전광역시 유성구 대학로 1",
                            "opnSfTeamCode": "3670000",
                            "x": "235000",
                            "y": "318000",
                            "apvPermYmd": "20260101",
                            "updateDt": "20260814010101",
                        }]
                    },
                    "totalCount": 1,
                },
            }
        }
        session = self.FakeSession(payload)
        stats = sync_localdata_api(
            dataset="rest_restaurant",
            dataset_config={
                "api_url": "https://example.test/rest_cafes/info",
                "category": "food_service",
            },
            service_key="test-key",
            session=session,
        )

        self.assertEqual(stats["created"], 1)
        record = SourcePlaceRecord.objects.get(source_record_id="API-1")
        self.assertEqual(record.category, "cafe")
        self.assertEqual(record.sigungu_name, "유성구")
        self.assertEqual(session.calls[0]["params"]["pageNo"], 1)


class SourcePlacePromotionTests(TestCase):
    def make_source_record(self, *, name="전국 브런치 카페", category="cafe"):
        reverse = Transformer.from_crs("EPSG:4326", "EPSG:5174", always_xy=True)
        x, y = reverse.transform(129.0756, 35.1796)
        return SourcePlaceRecord.objects.create(
            source="localdata",
            dataset="rest_restaurant",
            source_record_id="PROMOTE-1",
            name=name,
            category=category,
            business_type="커피숍",
            business_status="영업",
            is_active=True,
            address="부산광역시 부산진구 부전동 1",
            road_address="부산광역시 부산진구 중앙대로 1",
            sido_name="부산광역시",
            sigungu_name="부산진구",
            administrative_code="3290000",
            source_x=str(x),
            source_y=str(y),
            coordinate_reference_system="EPSG:5174",
        )

    def test_promotes_epsg5174_record_to_wgs84_place(self):
        record = self.make_source_record()

        stats = promote_records(SourcePlaceRecord.objects.all())

        self.assertEqual(stats["created"], 1)
        record.refresh_from_db()
        self.assertIsNotNone(record.normalized_place_id)
        self.assertAlmostEqual(record.normalized_place.lat, 35.1796, places=4)
        self.assertAlmostEqual(record.normalized_place.lng, 129.0756, places=4)
        self.assertEqual(record.normalized_place.category, "cafe")

    def test_generates_idempotent_objective_and_candidate_evidence(self):
        self.make_source_record()
        promote_records(SourcePlaceRecord.objects.all())
        queryset = SourcePlaceRecord.objects.select_related("normalized_place")

        first = generate_tags(queryset)
        second = generate_tags(queryset)

        self.assertEqual(first["matches"], 2)
        self.assertEqual(second["matches"], 2)
        self.assertEqual(PlaceTag.objects.count(), 2)
        self.assertEqual(PlaceTagEvidence.objects.count(), 2)
        cafe = PlaceTag.objects.get(tag__name="카페")
        brunch = PlaceTag.objects.get(tag__name="브런치")
        self.assertEqual(cafe.status, "confirmed")
        self.assertTrue(cafe.is_verified)
        self.assertEqual(brunch.status, "candidate")
        self.assertFalse(brunch.is_verified)
