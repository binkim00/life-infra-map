from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from recommendations.models import Place, Tag, PlaceTagEvidence, EvidenceReview
from recommendations.services.automatic_content_review import assess_content, auto_review_content
from recommendations.management.commands.process_tag_enrichment_queue import save_place_candidate_evidence
from recommendations.services.tag_evidence_aggregation import aggregate_tag_evidence, active_evidence


class AutomaticContentReviewTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(name="테스트커피 서면점", category="cafe", address="부산 부산진구 중앙대로 100", source="test", lat=35.1, lng=129.1)
        self.tag = Tag.objects.create(name="콘센트있음")

    def row(self, quote="테스트커피 서면점은 좌석마다 콘센트가 있어서 편리했어요.", **kwargs):
        return PlaceTagEvidence.objects.create(place=self.place, tag=self.tag, source="web_search", source_reference="https://example.com/article", evidence=quote, polarity="positive", context={"source_title": "부산 카페 후기"}, **kwargs)

    def test_old_content_auto_approved_without_admin_attestation(self):
        row = self.row(expires_at=timezone.now()-timedelta(days=300))
        self.assertEqual(auto_review_content(row), "approved")
        self.assertFalse(PlaceTagEvidence.objects.filter(source="admin_review").exists())
        self.assertFalse(active_evidence(self.place, self.tag).exists())
        aggregate_tag_evidence(self.place, self.tag)
        tag = self.place.place_tags.get()
        self.assertFalse(tag.is_verified)
        self.assertIn("과거 자료", tag.evidence)

    def test_collector_runs_policy_and_preserves_manual_rejection(self):
        result = {"source_url": "https://example.com/article", "polarity": "positive", "evidence_summary": "테스트커피 서면점에는 콘센트가 있어요.", "source_title": "부산 카페", "raw": {"channel": "web"}}
        row, _ = save_place_candidate_evidence(self.place, self.tag.name, result, observed_at=timezone.now())
        self.assertEqual(row.review.status, "approved")
        self.assertIsNone(row.review.reviewer_id)
        review = row.review
        review.status="rejected"; review.history=[{"mode":"manual"}];review.save()
        save_place_candidate_evidence(self.place,self.tag.name,result,observed_at=timezone.now())
        review.refresh_from_db()
        self.assertEqual(review.status,"rejected")

    def test_changed_auto_quote_is_rechecked(self):
        row = self.row()
        auto_review_content(row)
        row.evidence="테스트커피 서면점에는 콘센트가 없어요."
        row.save()
        self.assertEqual(auto_review_content(row),"pending")
        self.assertFalse(active_evidence(self.place,self.tag).exists())

    def test_duplicate_is_excluded_without_deletion(self):
        row=self.row();auto_review_content(row)
        other=self.row()
        self.assertEqual(auto_review_content(other),"rejected")
        self.assertEqual(PlaceTagEvidence.objects.count(),2)

    def test_limited_approval_is_preserved_but_never_searchable(self):
        row = self.row()
        self.assertEqual(
            auto_review_content(
                row,
                decision="limited",
                reason="place_identity_uncertain",
                run_key="second-pass",
            ),
            "approved_limited",
        )
        self.assertFalse(active_evidence(self.place, self.tag).exists())
        self.assertFalse(PlaceTagEvidence.objects.filter(source="admin_review").exists())
        review = EvidenceReview.objects.get(evidence=row)
        self.assertEqual(review.status, "approved_limited")
        self.assertEqual(review.history[-1]["run_key"], "second-pass")

    def test_branch_address_mismatch_held(self):
        row=self.row("테스트커피 서면점에 콘센트가 있어요. 부산 중앙대로 999")
        self.assertEqual(assess_content(row)[0],"hold")

    def test_branch_title_omission_allowed_with_exact_address(self):
        row=self.row("테스트커피에는 콘센트가 있어요. 부산 부산진구 중앙대로 100")
        self.assertEqual(assess_content(row)[0],"approve")

    def test_false_quiet_substring_and_hashtag_only_are_held(self):
        row=self.row("테스트커피 서면점은 포장마차 분위기가 있어요.")
        row.tag=Tag.objects.create(name="조용함")
        self.assertEqual(assess_content(row)[0],"hold")
        row.evidence="#테스트커피 서면점 #조용한 카페"
        self.assertEqual(assess_content(row)[0],"hold")

    def test_other_city_in_title_wins_over_food_style_in_body(self):
        row=self.row("테스트커피 서면점에서 부산 스타일 커피. 콘센트가 있어요.")
        row.context={"source_title":"양산 테스트커피 서면점 후기"}
        self.assertEqual(assess_content(row)[0],"hold")

    def test_backfill_snapshot_simulation_and_safe_replay(self):
        import hashlib,json
        from io import StringIO
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from django.core.management import call_command
        from recommendations.services import automatic_content_review as policy
        row=self.row(expires_at=timezone.now()-timedelta(days=1))
        plan={'run_key':'test-backfill','policy_hash':hashlib.sha256(Path(policy.__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
              'items':[{'id':row.id,'place_id':row.place_id,'tag_id':row.tag_id,'quote_hash':hashlib.sha256(row.evidence.encode()).hexdigest(),'observed_updated_at':str(row.updated_at),'decision':'approve','reason':'place_and_content_supported'}]}
        with TemporaryDirectory() as directory:
            path=Path(directory)/'manifest.json';path.write_text(json.dumps(plan),encoding='utf-8')
            call_command('apply_automatic_content_review',str(path),simulate=True,stdout=StringIO())
            self.assertFalse(EvidenceReview.objects.exists())
            for index in (1,2):
                folder=Path(directory)/f'backup{index}'
                call_command('apply_automatic_content_review',str(path),apply=True,backup_dir=str(folder),stdout=StringIO())
                self.assertTrue((folder/'originals.jsonl').is_file())
                self.assertTrue((folder/'receipt.jsonl').is_file())
            self.assertEqual(len(EvidenceReview.objects.get(evidence=row).history),1)
            row.refresh_from_db()
            self.assertEqual(str(row.updated_at),plan['items'][0]['observed_updated_at'])
