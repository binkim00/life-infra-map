from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token

from recommendations.models import (
    Place,
    PlaceTag,
    PlaceTagCollectionJob,
    PlaceTagEvidence,
    ProviderQuotaUsage,
    Tag,
)
from recommendations.services.operations_dashboard import refresh_operations_snapshot


@override_settings(ALLOWED_HOSTS=["localhost", "testserver"])
class OperationsDashboardTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="member", password="pass")
        self.admin = user_model.objects.create_user(username="operator", password="pass", is_staff=True)
        self.user_token = Token.objects.create(user=self.user)
        self.admin_token = Token.objects.create(user=self.admin)
        self.place = Place.objects.create(
            name="운영 지표 카페",
            category="cafe",
            address="서울특별시 중구 테스트로 1",
            lat=37.56,
            lng=126.98,
            source="test",
            external_id="operations-cafe",
        )
        self.tag = Tag.objects.create(name="조용함", tag_type="recommendation")
        self.place_tag = PlaceTag.objects.create(
            place=self.place,
            tag=self.tag,
            source="web_evidence",
            status="candidate",
            confidence=70,
        )
        self.evidence = PlaceTagEvidence.objects.create(
            place=self.place,
            tag=self.tag,
            source="naver_blog_search",
            source_reference="https://example.test/evidence",
            polarity="positive",
            confidence=70,
            evidence="조용한 카페",
            observed_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=30),
        )
        PlaceTagCollectionJob.objects.create(
            place=self.place,
            cycle_date=timezone.localdate(),
            status="completed",
            stats={"requests": 1, "new_evidences": 1, "new_active_evidences": 1},
            context={"budget_bucket": "candidate_hint"},
        )
        ProviderQuotaUsage.objects.create(
            provider="naver_search",
            usage_date=timezone.localdate(),
            daily_limit=25000,
            request_count=1,
            success_count=1,
        )
        refresh_operations_snapshot()

    def headers(self, token):
        return {"HTTP_AUTHORIZATION": f"Token {token.key}", "HTTP_HOST": "localhost"}

    def test_anonymous_and_normal_users_cannot_read_operations(self):
        anonymous = self.client.get("/api/recommendations/admin/operations/", HTTP_HOST="localhost")
        normal = self.client.get(
            "/api/recommendations/admin/operations/",
            **self.headers(self.user_token),
        )
        self.assertIn(anonymous.status_code, {401, 403})
        self.assertEqual(normal.status_code, 403)

    def test_admin_can_filter_dashboard(self):
        response = self.client.get(
            "/api/recommendations/admin/operations/?days=7&region=서울&category=cafe",
            **self.headers(self.admin_token),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["filters"], {"days": 7, "region": "서울", "category": "cafe"})
        self.assertEqual(payload["cumulative"]["places"], 1)
        self.assertEqual(payload["period"]["new_evidence"], 1)
        self.assertEqual(payload["strategies"][0]["strategy"], "candidate_hint")
        self.assertEqual(payload["search_performance"]["status"], "NOT_AVAILABLE")
        self.assertIn("feature_documents", payload["semantic_pilot"])
        self.assertFalse(payload["semantic_pilot"]["candidate_injection_enabled"])
        self.assertEqual(payload["focus_region"]["region"], "부산")
        self.assertIn("cafe", payload["focus_region"]["categories"])

    def test_invalid_filter_is_rejected(self):
        response = self.client.get(
            "/api/recommendations/admin/operations/?days=90",
            **self.headers(self.admin_token),
        )
        self.assertEqual(response.status_code, 400)

    def test_daily_growth_command_uses_shared_metrics(self):
        output = StringIO()
        call_command("report_daily_tag_growth", days=1, stdout=output)
        text = output.getvalue()
        self.assertIn("new_evidence=1", text)
        self.assertIn("strategy=candidate_hint", text)
