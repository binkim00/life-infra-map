from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from recommendations.models import Place, PlaceTagEvidence, Tag
from recommendations.services.ai_intent_planner import _canonicalize, build_ai_intent_plan
from recommendations.services.ai_search_orchestrator import (
    collect_db_candidates,
    _dedupe_candidates,
    _semantic_category_review,
    _top_up_ranked_candidates,
    run_ai_search,
)
from recommendations.services.canonical_tag_policy import canonical_tag_name, canonical_tags_in_text
from recommendations.services.naver_tag_evidence_provider import evidence_polarity
from recommendations.services.search_hard_gate import apply_common_hard_gate
from recommendations.services.web_tag_evidence_provider import CATEGORY_TAGS


@override_settings(CONVERSATIONAL_SEARCH_AI_ENABLED=False)
class CompositionalSituationProfileTests(SimpleTestCase):
    def test_ai_location_false_positive_from_situation_phrase_is_cleared(self):
        plan, errors = _canonicalize({
            'action': 'search',
            'frame': {
                'location_mode': 'explicit',
                'anchor_location': '가족모임할',
                'target_objects': ['식당'],
                'candidate_place_types': ['식당'],
                'result_match_terms': ['식당'],
                'constraints': [],
                'exclusions': [],
                'primary_search_queries': ['식당'],
                'secondary_search_queries': [],
            },
        }, raw_query='가족모임할 식당 추천해줘', lat=35.15, lng=129.06)

        self.assertEqual(errors, [])
        self.assertEqual(plan['frame']['location_mode'], 'current_context')
        self.assertEqual(plan['frame']['anchor_location'], '')

    def test_real_explicit_location_is_not_cleared(self):
        plan, errors = _canonicalize({
            'action': 'search',
            'frame': {
                'location_mode': 'explicit',
                'anchor_location': '서면역',
                'target_objects': ['식당'],
                'candidate_place_types': ['식당'],
                'result_match_terms': ['식당'],
                'constraints': [],
                'exclusions': [],
                'primary_search_queries': ['서면역 식당'],
                'secondary_search_queries': [],
            },
        }, raw_query='서면역 가족모임 식당 추천해줘', lat=35.15, lng=129.06)

        self.assertEqual(errors, [])
        self.assertEqual(plan['frame']['location_mode'], 'explicit')
        self.assertEqual(plan['frame']['anchor_location'], '서면역')

    def test_adjacent_words_do_not_create_a_child_companion_false_positive(self):
        frame = self._frame('테이크아웃 말고 오래 앉아 이야기할 카페 추천해줘')

        self.assertNotIn('children', frame['intent_dimensions']['companions'])
        self.assertIn('conversation', frame['intent_dimensions']['activities'])

    def test_free_wifi_does_not_create_a_second_generic_wifi_requirement(self):
        tags = canonical_tags_in_text('무료 와이파이 있는 카페')

        self.assertIn('무료와이파이', tags)
        self.assertNotIn('와이파이있음', tags)

    def test_wifi_is_a_feature_when_an_explicit_cafe_is_requested(self):
        frame = self._frame("부산대 근처 조용하고 와이파이 되는 작업 카페")

        self.assertEqual(frame["candidate_category_codes"], ["cafe"])
        self.assertIn("와이파이있음", frame["required_features"])
        self.assertIn("조용함", frame["required_features"])

    def test_contextual_preferences_do_not_become_unasked_hard_filters(self):
        frame = self._frame("연산동에서 단체석이나 개별룸이 있고 대화하기 좋은 카페")

        self.assertEqual(frame["candidate_category_codes"], ["cafe"])
        self.assertIn("장기체류좋음", frame["preferred_features"])
        self.assertNotIn("장기체류좋음", frame["constraints"])
        self.assertIn("테이크아웃전문", frame["avoid_features"])
        self.assertNotIn("테이크아웃전문", frame["exclusions"])

    def test_cafe_group_seating_does_not_trigger_restaurant_group_meal_rejection(self):
        frame = self._frame("연산동에서 단체석이나 개별룸이 있고 대화하기 좋은 카페")
        candidate = {
            "name": "연산 일반카페",
            "category": "cafe",
            "address": "부산광역시 연제구 연산동",
        }

        self.assertNotIn(
            "회식/단체 식사 요청과 맞지 않는 간단한 식사 후보",
            _semantic_category_review(candidate, frame),
        )

    def _frame(self, query):
        plan = build_ai_intent_plan(query)
        self.assertEqual(plan["action"], "search")
        return plan["frame"]

    def test_legacy_tag_names_resolve_to_one_canonical_vocabulary(self):
        self.assertEqual(canonical_tag_name("조용한"), "조용함")
        self.assertEqual(canonical_tag_name("와이파이"), "와이파이있음")
        self.assertEqual(canonical_tag_name("무료 와이파이"), "무료와이파이")

    def test_family_gathering_builds_soft_reusable_place_preferences(self):
        frame = self._frame("주말에 가족모임할 식당 추천해줘")

        self.assertIn("restaurant", frame["candidate_category_codes"])
        self.assertIn("family", frame["intent_dimensions"]["companions"])
        self.assertIn("gathering", frame["intent_dimensions"]["occasions"])
        self.assertIn("단체석있음", frame["preferred_features"])
        self.assertIn("예약가능", frame["preferred_features"])
        self.assertNotIn("단체석있음", frame["required_features"])

    def test_parents_query_does_not_turn_inferred_comfort_into_hard_requirements(self):
        frame = self._frame("부모님이랑 가기 좋은 식당 추천해줘")

        self.assertIn("parents", frame["intent_dimensions"]["companions"])
        self.assertIn("편한좌석", frame["preferred_features"])
        self.assertIn("대화하기좋음", frame["preferred_features"])
        self.assertNotIn("편한좌석", frame["required_features"])
        self.assertIn("계단접근만가능", frame["avoid_features"])

    def test_unseen_composed_sentence_combines_companions_time_and_activity(self):
        frame = self._frame("비 오는 주말에 어린아이랑 부모님 모시고 오래 이야기할 식당")

        self.assertEqual(
            set(frame["intent_dimensions"]["companions"]),
            {"children", "parents"},
        )
        self.assertIn("conversation", frame["intent_dimensions"]["activities"])
        self.assertIn("유아의자있음", frame["preferred_features"])
        self.assertIn("유모차접근", frame["preferred_features"])
        self.assertIn("대화하기좋음", frame["preferred_features"])
        self.assertIn("장기체류좋음", frame["preferred_features"])
        self.assertIn("주말휴일운영", frame["required_features"])

    def test_explicit_features_are_required_while_contextual_features_stay_preferred(self):
        frame = self._frame("오랜만에 친구들 만나서 주차되는 조용한 식당 추천해줘")

        self.assertIn("friends", frame["intent_dimensions"]["companions"])
        self.assertIn("reunion", frame["intent_dimensions"]["occasions"])
        self.assertIn("주차가능", frame["required_features"])
        self.assertIn("조용함", frame["required_features"])
        self.assertIn("대화하기좋음", frame["preferred_features"])
        self.assertIn("장기체류좋음", frame["preferred_features"])


class SemanticTopUpSafetyTests(SimpleTestCase):
    def test_semantic_search_does_not_top_up_with_category_only_candidate(self):
        candidate = {
            "id": "db:1",
            "candidate_source": "db",
            "pre_ai_evidence_level": "strong",
            "matched_evidence": [{
                "type": "structured_category_direct",
                "field": "category",
                "value": "restaurant",
            }],
            "confidence": "high",
            "recommendation_confidence": "high",
        }

        ranked, additions = _top_up_ranked_candidates(
            [], [candidate], [], limit=10, semantic_required=True,
        )

        self.assertEqual(ranked, [])
        self.assertEqual(additions, [])

    def test_supported_semantic_top_up_is_always_low_confidence(self):
        candidate = {
            "id": "db:1",
            "candidate_source": "db",
            "pre_ai_evidence_level": "strong",
            "matched_evidence": [{
                "type": "verified_tag_direct",
                "field": "verified_tags",
                "value": "대화하기좋음",
            }],
            "confidence": "high",
            "recommendation_confidence": "high",
        }

        ranked, additions = _top_up_ranked_candidates(
            [], [candidate], [], limit=10, semantic_required=True,
        )

        self.assertEqual(len(additions), 1)
        self.assertEqual(ranked[0]["confidence"], "low")
        self.assertEqual(ranked[0]["recommendation_confidence"], "low")
        self.assertTrue(ranked[0]["verification_required"])


class RestaurantDbBusinessQualityTests(TestCase):
    def _place(self, name, external_id, *, raw, lat=35.1578, quality=80):
        return Place.objects.create(
            name=name,
            category="restaurant",
            address="부산광역시 부산진구 중앙대로 테스트",
            lat=lat,
            lng=129.0592,
            source="localdata",
            external_id=external_id,
            data_quality_score=quality,
            raw=raw,
        )

    def test_meal_search_excludes_convenience_store_and_prioritizes_dining_registry(self):
        convenience = self._place(
            "지에스25서면역점", "restaurant-convenience",
            raw={"dataset": "rest_restaurant", "business_type": "백화점"},
            quality=100,
        )
        cafe_permit = self._place(
            "가다커피", "restaurant-cafe-permit",
            raw={"dataset": "general_restaurant", "business_type": "기타"},
            quality=99,
        )
        rest_food = self._place(
            "서면 간식점", "restaurant-rest-food",
            raw={"dataset": "rest_restaurant", "business_type": "기타 휴게음식점"},
            lat=35.1579,
        )
        commercial_food = self._place(
            "서면 김밥집", "restaurant-commercial-food",
            raw={"dataset": "commercial_store", "business_type": "김밥/만두/분식"},
            lat=35.1580,
        )
        general_food = self._place(
            "서면 중식당", "restaurant-general-food",
            raw={"dataset": "general_restaurant", "business_type": "중국식"},
            lat=35.1581,
        )

        candidates = collect_db_candidates(
            {
                "target_objects": ["식당"],
                "result_match_terms": ["식당"],
                "candidate_place_types": ["식당"],
                "candidate_category_codes": ["restaurant"],
                "primary_search_queries": ["근처 식당"],
                "constraints": [],
            },
            lat=35.1578,
            lng=129.0592,
            radius=5000,
            limit=10,
        )

        ids = [candidate["place_id"] for candidate in candidates]
        self.assertNotIn(convenience.id, ids)
        self.assertNotIn(cafe_permit.id, ids)
        self.assertEqual(ids[:3], [general_food.id, commercial_food.id, rest_food.id])
        self.assertEqual(candidates[0]["db_business_fit_reason"], "general_restaurant_registry")


class CrossSourcePlaceDeduplicationTests(SimpleTestCase):
    def test_same_name_with_nearby_coordinates_merges_cross_source_candidates(self):
        candidates = [
            {
                'id': 'db:1',
                'external_id': 'local-1',
                'candidate_source': 'db',
                'name': '갓잇 서면점',
                'address': '부산광역시 부산진구 전포대로209번길 22, 1층',
                'lat': 35.1556,
                'lng': 129.0641,
                'verified_tags': ['예약가능'],
                'matched_evidence': [{'type': 'verified_tag_direct', 'value': '예약가능'}],
            },
            {
                'id': 'kakao:123:식당',
                'external_id': '123',
                'candidate_source': 'kakao',
                'name': '갓잇 서면점',
                'address': '부산 부산진구 전포대로209번길 22',
                'lat': 35.15561,
                'lng': 129.06411,
                'kakao_place_url': 'https://place.map.kakao.com/123',
                'matched_evidence': [{'type': 'structured_category_direct', 'value': 'restaurant'}],
            },
        ]

        deduped = _dedupe_candidates(candidates)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]['id'], 'db:1')
        self.assertEqual(deduped[0]['duplicate_count'], 2)
        self.assertEqual(deduped[0]['duplicate_candidate_ids'], ['kakao:123:식당'])
        self.assertEqual(deduped[0]['kakao_place_url'], 'https://place.map.kakao.com/123')
        self.assertEqual(len(deduped[0]['matched_evidence']), 2)

    def test_same_franchise_name_at_distant_addresses_stays_separate(self):
        candidates = [
            {
                'id': 'db:1', 'external_id': 'local-1', 'name': '브랜드 식당',
                'address': '부산 부산진구 중앙대로 1', 'lat': 35.15, 'lng': 129.06,
            },
            {
                'id': 'db:2', 'external_id': 'local-2', 'name': '브랜드 식당',
                'address': '부산 해운대구 해운대로 2', 'lat': 35.16, 'lng': 129.16,
            },
        ]

        self.assertEqual(len(_dedupe_candidates(candidates)), 2)


class RestaurantAtomicEvidenceVocabularyTests(SimpleTestCase):
    def test_restaurant_collection_allows_reusable_group_and_access_features(self):
        restaurant_tags = set(CATEGORY_TAGS['restaurant'])
        self.assertTrue({
            '단체석있음', '예약가능', '개별룸있음', '유아의자있음',
            '유모차접근', '편한좌석', '테이크아웃전문', '좌석없음',
        }.issubset(restaurant_tags))

    def test_direct_positive_and_negative_phrases_are_grounded(self):
        cases = {
            '단체석있음': '8명이 함께 앉을 수 있는 단체석이 있다',
            '예약가능': '전화와 네이버로 예약 가능하다',
            '개별룸있음': '가족 모임용 개별 룸이 있다',
            '유아의자있음': '아기 의자를 요청할 수 있다',
            '테이크아웃전문': '매장 좌석이 없는 테이크아웃 전문점이다',
            '좌석없음': '포장 전문이라 매장 좌석이 없다',
        }
        for tag_name, text in cases.items():
            with self.subTest(tag_name=tag_name):
                self.assertEqual(
                    evidence_polarity(tag_name, text, category='restaurant'),
                    'positive',
                )

        self.assertEqual(
            evidence_polarity(
                '단체석있음', '단체석은 없고 2인석만 있다', category='restaurant',
            ),
            'negative',
        )

    def test_famous_named_dish_supports_distinctive_signature_menu(self):
        self.assertEqual(
            evidence_polarity(
                "대표메뉴뚜렷함",
                "싱싱한 해물과 야채가 들어간 이색 메뉴 라조면으로 유명한 중화요리 맛집입니다.",
                category="restaurant",
            ),
            "positive",
        )


class ExplicitSemanticHardGateTests(TestCase):
    def setUp(self):
        self.tag = Tag.objects.create(name="조용함", tag_type="recommendation")
        self.supported = Place.objects.create(
            name="조용한 식당",
            category="restaurant",
            address="부산광역시 부산진구",
            lat=35.15,
            lng=129.06,
            source="test",
            external_id="supported",
        )
        self.unsupported = Place.objects.create(
            name="일반 식당",
            category="restaurant",
            address="부산광역시 부산진구",
            lat=35.16,
            lng=129.07,
            source="test",
            external_id="unsupported",
        )
        PlaceTagEvidence.objects.create(
            place=self.supported,
            tag=self.tag,
            source="official",
            polarity="positive",
            confidence=90,
            evidence_key="quiet-supported",
            observed_at=timezone.now(),
        )

    def test_explicit_subjective_requirement_needs_active_positive_evidence(self):
        frame = {
            "candidate_category_codes": ["restaurant"],
            "target_objects": ["식당"],
            "result_match_terms": ["식당"],
            "required_features": ["조용함"],
            "structured_conditions": [],
        }
        candidates = [
            {"id": "db:1", "place_id": self.supported.id, "category": "restaurant", "address": self.supported.address},
            {"id": "db:2", "place_id": self.unsupported.id, "category": "restaurant", "address": self.unsupported.address},
        ]

        kept, removed, debug = apply_common_hard_gate(
            candidates,
            "조용한 식당",
            frame,
        )

        self.assertEqual([row["id"] for row in kept], ["db:1"])
        self.assertEqual([row["id"] for row in removed], ["db:2"])
        self.assertEqual(debug["removed_by_type"], {"feature": 1})


@override_settings(
    CONVERSATIONAL_SEARCH_AI_ENABLED=False,
    AI_SEARCH_MIN_STRONG_MEDIUM_CANDIDATES=0,
    SEMANTIC_RETRIEVAL_ENABLED=False,
    SEMANTIC_CANDIDATE_INJECTION_ENABLED=False,
)
class CompositionalSearchResponseIntegrationTests(TestCase):
    def setUp(self):
        self.quiet_tag = Tag.objects.create(name="조용함", tag_type="recommendation")
        self.supported = Place.objects.create(
            name="조용한 모임 식당",
            category="restaurant",
            address="부산광역시 부산진구",
            lat=35.15,
            lng=129.06,
            source="test",
            external_id="quiet-supported-response",
        )
        self.unsupported = Place.objects.create(
            name="일반 모임 식당",
            category="restaurant",
            address="부산광역시 부산진구",
            lat=35.151,
            lng=129.061,
            source="test",
            external_id="quiet-unsupported-response",
        )
        PlaceTagEvidence.objects.create(
            place=self.supported,
            tag=self.quiet_tag,
            source="official",
            polarity="positive",
            confidence=90,
            evidence_key="quiet-supported-response",
            observed_at=timezone.now(),
        )

    def _candidate(self, place, *, supported):
        evidence = {
            "type": "verified_tag_direct" if supported else "structured_category_direct",
            "field": "verified_tags" if supported else "category",
            "value": "조용함" if supported else "restaurant",
        }
        return {
            "id": f"db:{place.id}",
            "place_id": place.id,
            "candidate_source": "db",
            "source": "db",
            "name": place.name,
            "category": place.category,
            "address": place.address,
            "lat": place.lat,
            "lng": place.lng,
            "distance": 100,
            "score": 80,
            "pre_ai_evidence_level": "strong",
            "evidence_level": "strong",
            "matched_evidence": [evidence],
        }

    @patch(
        "recommendations.services.ai_search_orchestrator.collect_kakao_candidates",
        return_value=([], []),
    )
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates")
    def test_final_response_excludes_place_without_explicit_quiet_evidence(
        self,
        mock_db_candidates,
        _mock_kakao_candidates,
    ):
        mock_db_candidates.return_value = [
            self._candidate(self.supported, supported=True),
            self._candidate(self.unsupported, supported=False),
        ]

        data = run_ai_search({
            "query": "오랜만에 친구들 만나서 조용한 식당 추천해줘",
            "lat": 35.15,
            "lng": 129.06,
            "limit": 10,
        })

        self.assertEqual(data["decision_action"], "search")
        self.assertEqual(
            [row["id"] for row in data["results"]],
            [f"db:{self.supported.id}", f"db:{self.unsupported.id}"],
        )
        self.assertLess(
            data["results"][0]["result_quality_sort_key"],
            data["results"][1]["result_quality_sort_key"],
        )
        self.assertTrue(
            any("조용" in condition for condition in data["results"][0]["matched_conditions"])
        )
        fallback = data["results"][1]
        self.assertEqual(fallback["result_tier"], "best_available")
        self.assertTrue(
            any("조용" in condition for condition in fallback["missing_conditions"])
        )
        self.assertTrue(
            any(word in fallback["recommendation_reason"] for word in ("부족", "확인"))
        )
        self.assertEqual(
            data["debug_pipeline"]["reranker"]["common_hard_gate"]["removed_by_type"],
            {"feature": 1},
        )

    @patch(
        "recommendations.services.ai_search_orchestrator.collect_kakao_candidates",
        return_value=([], []),
    )
    @patch("recommendations.services.ai_search_orchestrator.collect_db_candidates")
    def test_contextual_parent_preferences_do_not_become_final_response_hard_gates(
        self,
        mock_db_candidates,
        _mock_kakao_candidates,
    ):
        mock_db_candidates.return_value = [
            self._candidate(self.unsupported, supported=False),
        ]

        data = run_ai_search({
            "query": "부모님이랑 가기 좋은 식당 추천해줘",
            "lat": 35.15,
            "lng": 129.06,
            "limit": 10,
        })

        self.assertEqual(data["decision_action"], "search")
        self.assertEqual([row["id"] for row in data["results"]], [f"db:{self.unsupported.id}"])
        self.assertEqual(
            data["debug_pipeline"]["reranker"]["common_hard_gate"]["removed_count"],
            0,
        )
