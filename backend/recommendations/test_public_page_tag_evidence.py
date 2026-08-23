from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from recommendations.services.public_page_tag_evidence import (
    PageTextParser, evidence_span, extract_page_evidences, fetch_public_page,
    normalize_page_polarity, polarity_assessment, relevant_page_text, safe_public_url,
)


class PlaceStub:
    id = 1
    name = "카페봄"
    category = "cafe"
    address = "부산광역시 부산진구 전포동 1"
    detail_location = ""
    raw = {}
    source = "kakao"


class ResponseStub:
    def __init__(self, *, status=200, content_type="text/html", body=b"", location=""):
        self.status_code = status
        self.headers = {"Content-Type": content_type, "Location": location}
        self.encoding = "utf-8"
        self.text = body.decode("utf-8", errors="replace")
        self._body = body

    def iter_content(self, _size):
        yield self._body


@override_settings(PUBLIC_PAGE_FETCH_MIN_TEXT_LENGTH=20, PUBLIC_PAGE_FETCH_MAX_BYTES=10000)
class PublicPageEvidenceTests(SimpleTestCase):
    @patch("recommendations.services.public_page_tag_evidence.safe_public_url", return_value=("https://example.com/post", ""))
    @patch("recommendations.services.public_page_tag_evidence.robots_allowed", return_value=True)
    def test_fetch_rejects_non_html(self, _robots, _safe):
        session = Mock()
        session.get.return_value = ResponseStub(content_type="application/pdf", body=b"pdf")
        self.assertEqual(fetch_public_page("https://example.com/post", session=session)["error"], "CONTENT_TYPE_REJECT")

    @patch("recommendations.services.public_page_tag_evidence.safe_public_url", return_value=("https://example.com/post", ""))
    @patch("recommendations.services.public_page_tag_evidence.robots_allowed", return_value=True)
    def test_fetch_rejects_short_body(self, _robots, _safe):
        session = Mock()
        session.get.return_value = ResponseStub(body="<html><body>짧음</body></html>".encode())
        self.assertEqual(fetch_public_page("https://example.com/post", session=session)["error"], "BODY_TOO_SHORT")

    @patch("recommendations.services.public_page_tag_evidence.safe_public_url", return_value=("https://example.com/post", ""))
    @patch("recommendations.services.public_page_tag_evidence.robots_allowed", return_value=True)
    def test_fetch_extracts_body_and_unknown_publication_date(self, _robots, _safe):
        session = Mock()
        session.get.return_value = ResponseStub(body=("<html><title>카페봄 후기</title><body>"
            "부산 전포동 카페봄은 창가 자리에 콘센트가 있다. 노트북 작업하기 좋다."
            "</body></html>").encode())
        result = fetch_public_page("https://example.com/post", session=session)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["published_at"])
        self.assertIn("콘센트", result["text"])

    def test_page_extracts_multiple_tags_and_negative(self):
        page = {
            "url": "https://example.com/post", "title": "부산 전포 카페봄 방문 후기",
            "text": "부산 전포동 카페봄은 콘센트가 있고 노트북 작업하기 좋다. 오래 있어도 편했다. 장시간 노트북 사용 금지는 아니다.",
            "published_at": "2026-08-01",
        }
        with patch("recommendations.services.public_page_tag_evidence.identity_assessment", return_value={"matched": True, "score": 90}):
            result = extract_page_evidences(PlaceStub(), page)
        tags = {row["tag_name"] for row in result["evidences"]}
        self.assertIn("콘센트있음", tags)
        self.assertIn("노트북작업", tags)
        self.assertIn("작업하기좋음", tags)

    def test_page_requires_exact_title_and_strong_identity(self):
        page = {"url": "https://example.com/post", "title": "다른 카페 후기", "text": "카페봄 근처는 조용하다.", "published_at": None}
        with patch("recommendations.services.public_page_tag_evidence.identity_assessment", return_value={"matched": True, "score": 90}):
            result = extract_page_evidences(PlaceStub(), page)
        self.assertEqual(result["error"], "IDENTITY_MISMATCH")

    def test_related_place_section_is_removed(self):
        text = "카페봄은 조용하다. 카페봄 와 비슷한 맛집 현 식당에서 200m 다른카페는 카공하기 좋다."
        relevant = relevant_page_text(text)
        self.assertIn("카페봄은 조용하다", relevant)
        self.assertNotIn("다른카페", relevant)

    def test_evidence_span_keeps_verbatim_sentence(self):
        text = "첫 문장이다. 창가 자리에 콘센트가 있어 노트북 작업하기 좋다. 마지막이다."
        span = evidence_span(text, {"positive_terms": ["콘센트"], "negative_terms": [], "supporting_terms": []})
        self.assertIn("콘센트", span)
        self.assertNotIn("첫 문장", span)

    def test_hashtag_only_feature_is_not_evidence(self):
        text = "#부산카페 #부산데이트코스 #부산여행 태그 취소 확인"
        span = evidence_span(text, {"positive_terms": ["데이트 코스"], "negative_terms": [], "supporting_terms": []})
        self.assertEqual(span, "")

    def test_navigation_title_is_not_evidence_span(self):
        text = "분위기 좋은 카페 : 네이버 블로그 NAVER 블로그 블로그 검색"
        span = evidence_span(text, {"positive_terms": ["분위기 좋은"], "negative_terms": [], "supporting_terms": []})
        self.assertEqual(span, "")

    def test_wifi_x_becomes_contradicting(self):
        result = normalize_page_polarity("무료와이파이", "무선인터넷 / 와이파이 여부 : X", {"polarity": "positive", "strength": "DIRECT", "clarity_score": 80})
        self.assertEqual(result["polarity"], "negative")

    def test_cafe_work_not_recommended_becomes_contradicting(self):
        result = normalize_page_polarity("노트북작업", "카공할 분위기는 아니니까 참고", {"polarity": "positive", "strength": "DIRECT", "clarity_score": 80})
        self.assertEqual(result["polarity"], "negative")

    def test_waiting_double_negative_becomes_positive(self):
        result = normalize_page_polarity("웨이팅적음", "오래 기다리진 않았고 바로 들어갔다", {"polarity": "negative", "strength": "CONTRADICTING", "clarity_score": 80})
        self.assertEqual(result["polarity"], "positive")

    def test_less_crowded_quiet_context_becomes_positive(self):
        result = normalize_page_polarity(
            "조용함", "북적거림보다는 한산한 느낌이고 아무도 없다", {"polarity": "negative", "strength": "CONTRADICTING", "clarity_score": 80}
        )
        self.assertEqual(result["polarity"], "positive")
        self.assertEqual(result["strength"], "SUPPORTING")

    def test_solo_meal_visit_without_appraisal_is_supporting(self):
        result = normalize_page_polarity(
            "혼밥좋음", "제가 오늘 혼밥을 했어요", {"polarity": "positive", "strength": "DIRECT", "clarity_score": 85}
        )
        self.assertEqual(result["polarity"], "positive")
        self.assertEqual(result["strength"], "SUPPORTING")

    def test_solo_seat_comparison_is_negative(self):
        result = normalize_page_polarity(
            "혼자이용좋음", "좌석은 혼자 앉기보다", {"polarity": "positive", "strength": "DIRECT", "clarity_score": 80}
        )
        self.assertEqual(result["polarity"], "negative")

    def test_generic_time_spent_is_long_stay_supporting(self):
        result = normalize_page_polarity(
            "장기체류좋음", "조용히 시간 보내기 좋았던 카페", {"polarity": "positive", "strength": "DIRECT", "clarity_score": 80}
        )
        self.assertEqual(result["strength"], "SUPPORTING")

    def test_embedded_external_link_sentence_is_not_evidence(self):
        extraction = {"positive_terms": ["혼밥"], "negative_terms": [], "supporting_terms": []}
        self.assertEqual(
            evidence_span("https://blog.naver.com/example 손칼국수 혼밥 후기", extraction),
            "",
        )

    def test_date_not_suitable_phrase_is_negative(self):
        result = normalize_page_polarity(
            "데이트좋음", "데이트 하기 좋은 분위기는 아님", {"polarity": "positive", "strength": "DIRECT", "clarity_score": 80}
        )
        self.assertEqual(result["polarity"], "negative")

    def test_product_packaging_mood_is_not_venue_atmosphere(self):
        text = "리본 패키지들이 감성적인 느낌으로 포장되어 있다."
        extraction = polarity_assessment("분위기좋음", text, category="cafe")
        span = evidence_span(text, extraction)
        self.assertTrue(span)
        compact_span = "".join(span.split())
        venue_context = ("분위기", "공간", "매장", "카페", "식당", "내부", "인테리어", "좌석")
        self.assertFalse(any("".join(term.split()) in compact_span for term in venue_context))

    def test_parking_long_duration_is_not_long_stay(self):
        page = {"url": "https://example.com/post", "title": "카페봄 방문 후기", "text": "장시간 이용시 인근 주차장을 이용해 주세요.", "published_at": None}
        with patch("recommendations.services.public_page_tag_evidence.identity_assessment", return_value={"matched": True, "score": 90}):
            result = extract_page_evidences(PlaceStub(), page)
        self.assertNotIn("장기체류좋음", {row["tag_name"] for row in result["evidences"]})

    def test_html_parser_ignores_script(self):
        parser = PageTextParser()
        parser.feed("<html><script>콘센트 있음</script><body>실제 본문</body></html>")
        self.assertNotIn("콘센트", " ".join(parser.text))

    def test_html_parser_records_explicit_public_post_frame(self):
        parser = PageTextParser()
        parser.feed('<iframe src="/PostView.naver?blogId=test&amp;logNo=1"></iframe>')
        self.assertEqual(parser.frames, ["/PostView.naver?blogId=test&logNo=1"])

    def test_naver_smarteditor_main_body_excludes_navigation(self):
        parser = PageTextParser()
        parser.feed('<div>커플 여행 블로그</div><div class="se-main-container"><p>카페봄은 콘센트가 있어 작업하기 좋아요.</p></div><div>다른 글 데이트</div>')
        body = " ".join(parser.main_text)
        self.assertIn("콘센트", body)
        self.assertNotIn("커플", body)
        self.assertNotIn("다른 글", body)

    def test_autogenerated_place_directory_is_blocked_before_fetch(self):
        url, reason = safe_public_url("https://place.udanax.org/p/1/example")
        self.assertEqual(url, "")
        self.assertEqual(reason, "SOURCE_REJECT")
