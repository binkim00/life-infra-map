from datetime import timedelta
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Place, Tag, PlaceTagEvidence, EvidenceReview, PlaceReport
from .services.tag_evidence_aggregation import active_evidence


class MobileAdminWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = get_user_model().objects.create_user(username="review-admin", is_staff=True)
        self.user = get_user_model().objects.create_user(username="report-owner")
        self.other = get_user_model().objects.create_user(username="other-owner")
        self.place = Place.objects.create(name="검토 장소", category="cafe", lat=35.1, lng=129.1, source="test")
        self.tag = Tag.objects.create(name="조용함")
        self.evidence = PlaceTagEvidence.objects.create(place=self.place, tag=self.tag, source="web_search", source_reference="https://example.org/quote", evidence="조용한 공간", expires_at=timezone.now()+timedelta(days=1))

    def test_queue_requires_admin_and_lists_unreviewed_evidence(self):
        url = "/api/recommendations/admin/evidence/"
        self.assertIn(self.client.get(url).status_code, [401, 403])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["quote"], "조용한 공간")

    def test_research_audits_are_admin_only_and_preserve_missing_judgments(self):
        from .models import ResearchAudit
        ResearchAudit.objects.create(run_key="validation-test.json", payload={"rows": 50, "rejected": 23})
        url = "/api/recommendations/admin/research-audits/"
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.admin)
        payload = self.client.get(url).data["results"][0]["payload"]
        self.assertEqual(payload["rejected"], 23)
        self.assertNotIn("judgments", payload)

    def test_review_preserves_source_and_excludes_rejected_evidence(self):
        self.client.force_authenticate(self.admin)
        url = f"/api/recommendations/admin/evidence/{self.evidence.id}/"
        self.assertEqual(self.client.post(url, {"status": "approved", "note": ""}).status_code, 400)
        self.assertEqual(self.client.post(url, {"status": "approved", "note": "원문 장소 일치 확인"}).status_code, 200)
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.source, "web_search")
        self.assertEqual(self.client.post(url, {"status": "rejected", "note": "다른 장소 인용임을 확인"}).status_code, 200)
        self.assertFalse(active_evidence(self.place, self.tag).exists())
        self.assertEqual(len(EvidenceReview.objects.get(evidence=self.evidence).history), 2)

    def test_expired_evidence_cannot_be_approved(self):
        self.evidence.expires_at = timezone.now()-timedelta(days=1)
        self.evidence.save()
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/recommendations/admin/evidence/{self.evidence.id}/", {"status": "approved", "note": "검토"})
        self.assertEqual(response.status_code, 400)

    def test_report_detail_is_owner_only_and_includes_description(self):
        report = PlaceReport.objects.create(user=self.user, report_type="new_place", suggested_name="제보 장소", description="출입구 위치를 확인해 주세요.")
        url = f"/api/recommendations/place-reports/{report.id}/"
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(url).data["description"], report.description)
        self.assertEqual(self.client.get("/api/recommendations/place-reports/").data["results"][0]["description"], report.description)

    def test_report_accepts_device_coordinates_with_more_than_six_decimals(self):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/recommendations/place-reports/", {
            "report_type": "new_place", "suggested_name": "GPS 제보",
            "suggested_lat": "35.0964659", "suggested_lng": "128.8539118",
            "description": "기기 좌표 정규화 검사", "suggested_tags": "[]",
        }, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        report = PlaceReport.objects.get(pk=response.data["report"]["id"])
        self.assertEqual(str(report.suggested_lat), "35.096466")
        self.assertEqual(str(report.suggested_lng), "128.853912")

    def test_report_retry_replays_the_same_receipt_without_duplicate_images_or_rows(self):
        self.client.force_authenticate(self.user)
        request_id = str(uuid.uuid4())
        payload = {
            "client_request_id": request_id,
            "report_type": "new_place",
            "suggested_name": "재시도 제보",
            "suggested_lat": "35.100000",
            "suggested_lng": "129.100000",
            "description": "응답 유실 재시도 검사",
            "suggested_tags": "[]",
        }
        first = self.client.post("/api/recommendations/place-reports/", payload, format="multipart")
        replay = self.client.post("/api/recommendations/place-reports/", payload, format="multipart")

        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data["report"]["id"], first.data["report"]["id"])
        self.assertTrue(replay.data["idempotent_replay"])
        self.assertEqual(PlaceReport.objects.filter(user=self.user, client_request_id=request_id).count(), 1)

    def test_same_request_key_returns_original_receipt_even_if_retry_body_changed(self):
        self.client.force_authenticate(self.user)
        request_id = str(uuid.uuid4())
        payload = {
            "client_request_id": request_id,
            "report_type": "new_place",
            "suggested_name": "원본 제보",
            "suggested_lat": "35.100000",
            "suggested_lng": "129.100000",
            "description": "원본",
        }
        first = self.client.post("/api/recommendations/place-reports/", payload, format="multipart")
        payload["suggested_name"] = "수정된 재시도"
        replay = self.client.post("/api/recommendations/place-reports/", payload, format="multipart")

        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data["report"]["id"], first.data["report"]["id"])
        self.assertEqual(replay.data["report"]["suggested_name"], "원본 제보")

    @patch("recommendations.views.search_places_by_keyword")
    def test_summary_preserves_place_identity_without_provider_raw(self, search):
        search.return_value = {"documents": [{"id": "123", "place_name": "유일상호", "x": "129.1", "y": "35.1", "place_url": "https://example.org/place"}]}
        response = self.client.get("/api/recommendations/place-search/", {"q": "유일상호", "source": "kakao", "detail_level": "summary"})
        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertEqual(row["name"], "유일상호")
        self.assertEqual(row["place_url"], "https://example.org/place")
        self.assertNotIn("raw", row)
