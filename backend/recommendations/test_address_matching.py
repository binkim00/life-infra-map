from django.test import SimpleTestCase

from recommendations.models import Place, PlaceTagEvidence, Tag
from recommendations.services.automatic_content_review import assess_content, matching_address


class AddressMatchingTests(SimpleTestCase):
    def test_real_address_shapes_preserve_number_boundaries(self):
        cases = [
            ("부산 중구 대청로141번길 5", "부산 중구 대청로141번길 5 1층 점보수제돈까스"),
            ("부산 동구 고관로 164", "부산 동구 고관로 164, 1층에 위치"),
            ("부산 부산진구 엄광로 143", "부산 부산진구 엄광로 143 0507-1234-5678"),
            ("서울 관악구 양지길 63", "원신공영주차장 서울 관악구 양지길 63 주차 안내"),
            ("부산 중구 중앙대로 2", "부산광역시 중구 중앙대로 2 본관 지하 1층"),
            ("부산 사상구 냉정로 49", "부산 사상구 냉정로 49 1층 동주집"),
            ("서울 서초구 양재동 동산로 13길 35", "서울특별시 서초구 동산로13길 35 (양재동)"),
            ("서울 서초구 동산로13길 35", "서울 서초구 동산로 13길 35"),
            ("부산 중구 중구로5번길 5", "부산광역시 중구 중구 로5번길 5, 1층"),
            ("부산 부산진구 중앙대로 100", "부산 부산진구 중앙 대로 100"),
            ("부산 남구 진남로 7-7", "부산 남구 진남로 7 - 7 1층"),
            ("부산 남구 진남로 7-7", "부산 남구 진남로 7–7"),
            ("서울 서초구 양재동 237", "서초구 양재동 237-0 24시간 운영"),
            ("서울 서초구 양재동 237-0", "서울 서초구 양재동237 주차장"),
            ("서울특별시 서초구 양재동 237", "서초구 양재동 237-0 24시간 운영 143면 10분당 500원 (1시간 3,000원)"),
            ("부산 기장군 기장읍 내리 346-6", "부산광역시 기장군 기장읍 내리 346-6"),
            ("부산 중구 남포동2가 19-3", "부산 중구 남포동2가 19 - 3"),
            ("경기 성남시 분당구 정자동 산 23-1", "경기도 성남시 분당구 정자동 산23-1"),
            ("경기도 광주시 중앙로 100", "경기 광주시 중앙로 100"),
            ("부산 중구 중앙대로 2 1층", "부산 중구 중앙대로 2, 1층"),
            ("부산 중구 중앙대로 2 지하 1층", "부산 중구 중앙대로 2 지하1층"),
        ]
        for address, prose in cases:
            with self.subTest(address=address, prose=prose):
                self.assertTrue(matching_address(address, prose))

    def test_other_building_or_parcel_numbers_never_match(self):
        cases = [
            ("보문로34길 69", "보문로34길 691"),
            ("보문로34길 691", "보문로34길 69 1층"),
            ("보문로34길 69", "보문로34길 69-1"),
            ("보문로34길 69-1", "보문로34길 69"),
            ("보문로34길 69-1", "보문로34길 691"),
            ("보문로34길 69-1", "보문로34길 69-10"),
            ("보문로34길 69-10", "보문로34길 69-1"),
            ("중앙대로 100", "중앙대로 100/1"),
            ("중앙대로 100", "중앙대로 100-1-2"),
            ("동산로 13", "동산로13길 35"),
            ("중앙대로 100", "중앙대로100번길 5"),
            ("중앙대로 100", "신중앙대로 100"),
            ("중앙대로 100", "중앙대로 100층"),
            ("중앙대로 100", "중앙대로 100호"),
            ("중앙대로 100", "중앙대로 100층에 있어요"),
            ("양재동 237", "양재동 237호에 있어요"),
            ("양재동 237", "양재동 237-2"),
            ("양재동 237-2", "양재동 237-0"),
            ("양재동 237-2", "양재동 2372"),
            ("양재동 237", "양재동 2370"),
            ("양재동 237", "양재동 산237"),
            ("양재동 산237", "양재동 237"),
            ("양재동 237", "신양재동 237"),
            ("내리1길 13", "내리 346-6"),
            ("", "서울 서초구 양재동 237"),
            ("서울 서초구 양재동 237", "서초구의 주차장"),
            # A parenthesized dong without independent type context is held.
            ("서울 서초구 동산로 13길 35", "서울특별시 서초구 동산로13길 35 (양재동)"),
            ("보문로34길 69", "보문로34길 69에서 보문로34길 691로 이전"),
            ("부산 중구 중앙대로 2 1층", "부산 중구 중앙대로 2 2층"),
            ("부산 중구 중앙대로 2 1층", "부산 중구 중앙대로 2 지하1층"),
            ("부산 중구 중앙대로 2 101호", "부산 중구 중앙대로 2 102호"),
        ]
        for address, prose in cases:
            with self.subTest(address=address, prose=prose):
                self.assertFalse(matching_address(address, prose))

    def test_identical_road_or_lot_in_another_region_is_not_equal(self):
        cases = [
            ("부산 부산진구 중앙대로 100", "대구 중구 중앙대로 100"),
            ("부산 부산진구 중앙대로 100", "부산 중구 중앙대로 100"),
            ("부산 부산진구 중앙대로 100", "부산 여행 뒤 방문한 대구 중구 중앙대로 100"),
            ("부산 부산진구 중앙대로 100", "부산 부산진구 중앙대로 100; 대구 중구 중앙대로 100"),
            ("경기 수원시 중앙로 100", "경기도 성남시 중앙로 100"),
            ("경기도 광주시 중앙로 100", "광주광역시 중앙로 100"),
            ("광주광역시 중앙로 100", "경기도 광주시 중앙로 100"),
            ("부산 중앙로 100", "광주시 중앙로 100"),
            ("서울 서초구 양재동 237", "경기도 다른시 양재동 237"),
            ("서울 서초구 양재동 237", "서울 강남구 양재동 237"),
            ("부산 기장군 기장읍 내리 346-6", "부산 기장군 장안읍 내리 346-6"),
        ]
        for address, prose in cases:
            with self.subTest(address=address, prose=prose):
                self.assertFalse(matching_address(address, prose))


class AddressReviewIntegrationTests(SimpleTestCase):
    def row(self, address, prose, *, name="테스트커피 서면점", title=None, tag="콘센트있음"):
        return PlaceTagEvidence(
            place=Place(name=name, address=address, category="cafe", source="test", lat=35.1, lng=129.1),
            tag=Tag(name=tag), source="web_search", polarity="positive",
            source_reference="https://example.com/article", evidence=prose,
            context={"source_title": title or f"{name} 후기"},
        )

    def test_address_fixes_reach_existing_claim_checks_without_database_access(self):
        cases = [
            ("부산 부산진구 중앙대로 100", "부산 부산진구 중앙대로 100 1층"),
            ("부산 부산진구 중앙대로 100", "부산 부산진구 중앙대로 100 0507-1234-5678"),
            ("부산 중구 중앙대로 2", "부산 중구 중앙대로 2"),
            ("서울 서초구 동산로 13길 35", "서울 서초구 동산로13길 35"),
            ("서울 서초구 양재동 237", "서울 서초구 양재동 237-0"),
        ]
        for address, location in cases:
            with self.subTest(address=address, location=location):
                row = self.row(address, f"{location} 테스트커피 서면점은 좌석마다 콘센트가 있어서 편리해요.")
                original = row.evidence
                self.assertEqual(assess_content(row)[0], "approve")
                self.assertIsNone(row.pk)
                self.assertEqual(row.evidence, original)

    def test_wrong_region_in_prose_is_not_rescued_by_correct_region_in_title(self):
        row = self.row(
            "부산 부산진구 중앙대로 100",
            "대구 중구 중앙대로 100 테스트커피 서면점에는 콘센트가 있어요.",
            title="부산 테스트커피 서면점 후기",
        )
        self.assertEqual(assess_content(row), ("hold", "different_address_needs_branch_or_move_check"))

    def test_same_brand_other_branch_is_held_even_at_the_same_address(self):
        for title, quote_name in [
            ("테스트커피 연산점 후기", "테스트커피 연산점"),
            ("테스트커피 서면점 후기", "테스트커피 연산점"),
            ("테스트커피 연산점 후기", "테스트커피 서면점"),
            ("테스트커피 후기", "테스트커피"),
        ]:
            with self.subTest(title=title, quote_name=quote_name):
                row = self.row(
                    "부산 중구 중앙대로 2",
                    f"부산 중구 중앙대로 2 {quote_name}에는 콘센트가 있어요.", title=title,
                )
                self.assertEqual(assess_content(row)[0], "hold")

    def test_correct_branch_name_does_not_override_different_building(self):
        row = self.row("부산 중구 중앙대로 2", "부산 중구 중앙대로 21 테스트커피 서면점에는 콘센트가 있어요.")
        self.assertEqual(assess_content(row), ("hold", "different_address_needs_branch_or_move_check"))

    def test_matching_address_does_not_approve_other_business_or_hashtags(self):
        quotes = [
            "부산 중구 중앙대로 2 테스트커피 서면점 맞은편 다른 카페에는 콘센트가 있어요.",
            "부산 중구 중앙대로 2 #테스트커피서면점 #콘센트있음",
        ]
        for quote in quotes:
            with self.subTest(quote=quote):
                self.assertEqual(assess_content(self.row("부산 중구 중앙대로 2", quote))[0], "hold")

    def test_matching_address_preserves_opposite_and_human_review_gates(self):
        row = self.row("부산 중구 중앙대로 2", "부산 중구 중앙대로 2 테스트커피 서면점에는 콘센트가 없어요.")
        self.assertEqual(assess_content(row), ("reject", "explicit_opposite_statement"))
        row = self.row(
            "부산 중구 중앙대로 2",
            "부산 중구 중앙대로 2 테스트커피 서면점은 혼밥 하기 좋아요.", tag="혼밥좋음",
        )
        self.assertNotEqual(assess_content(row)[0], "approve")

    def test_review_regressions_do_not_approve_conflicting_addresses(self):
        cases = [
            ("부산 중구 중앙대로 2", "대구 중구, 중앙대로 2 테스트커피 서면점에는 콘센트가 있어요."),
            ("부산 중구 중앙대로 2", "대구 중구\n중앙대로 2 테스트커피 서면점에는 콘센트가 있어요."),
            ("부산 중구 중앙대로 2", "대구 중구 / 중앙대로 2 테스트커피 서면점에는 콘센트가 있어요."),
            ("부산 부산진구 중앙대로 2", "부산 중구(중앙동) 중앙대로 2 테스트커피 서면점에는 콘센트가 있어요."),
            ("부산 중구 중앙대로 100 1층", "부산 중구 중앙대로 100\n2층 테스트커피 서면점에는 콘센트가 있어요."),
            ("부산 중구 중앙대로 100 101호", "부산 중구 중앙대로 100\n102호 테스트커피 서면점에는 콘센트가 있어요."),
            ("부산 중구 중앙대로 2 1층", "부산 중구 중앙대로 2 B1 테스트커피 서면점에는 콘센트가 있어요."),
            ("부산 중구 중앙대로 2", "테스트커피 서면점은 부산 중구 중앙대로 2에서 부산 중구 광복로 10으로 이전했습니다. 새 매장에는 콘센트가 있어요."),
            ("부산 중구 중앙대로 100", "대구 중구, 중앙대로 100 테스트커피 서면점에는 콘센트가 있어요."),
            ("부산 중구 중앙대로 100", "테스트커피 서면점은 부산 중구 중앙대로 100에서 부산 중구 광복로 10으로 이전했습니다. 새 매장에는 콘센트가 있어요."),
        ]
        for address, prose in cases:
            with self.subTest(address=address, prose=prose):
                self.assertFalse(matching_address(address, prose))
                self.assertEqual(
                    assess_content(self.row(address, prose, title="부산 테스트커피 서면점 후기")),
                    ("hold", "different_address_needs_branch_or_move_check"),
                )

    def test_other_branch_containing_registered_name_is_held(self):
        for number in ("2", "100"):
            for other_name in (
                "테스트커피 서면점2호점", "테스트커피 서면점 2호점",
                "테스트커피 서면점별관", "테스트커피 서면점 별관", "신테스트커피 서면점",
            ):
                for title_name, quote_name in (
                    (other_name, other_name), ("테스트커피 서면점", other_name),
                    (other_name, "테스트커피 서면점"),
                    ("테스트커피 서면점", f"테스트커피 서면점과 {other_name}"),
                ):
                    with self.subTest(number=number, title=title_name, quote=quote_name):
                        row = self.row(
                            f"부산 중구 중앙대로 {number}",
                            f"부산 중구 중앙대로 {number} {quote_name}에는 콘센트가 있어요.",
                            title=f"{title_name} 후기",
                        )
                        self.assertEqual(assess_content(row)[0], "hold")

    def test_matching_multiline_address_and_name_particles_remain_approved(self):
        cases = [
            ("부산 중구 중앙대로 2", "부산 중구,\n중앙대로 2"),
            ("부산 중구 중앙대로 2", "부산 중구(중앙동) 중앙대로 2"),
            ("부산 중구 중앙대로 100 1층", "부산 중구 중앙대로 100\n1층"),
            ("부산 중구 중앙대로 100 101호", "부산 중구 중앙대로 100\n101호"),
            ("부산 중구 중앙대로 2 지하 1층", "부산 중구 중앙대로 2\nB1"),
            ("부산 중구 중앙대로 2 B1F", "부산 중구 중앙대로 2 지하1층"),
            ("부산 중구 중앙대로 2 지하1층", "부산 중구 중앙대로 2 B 1 F"),
            ("부산 중구 중앙대로 2 지하1층", "부산 중구 중앙대로 2 B1층"),
            ("부산 중구 중앙대로 2 1F", "부산 중구 중앙대로 2\n1층"),
            ("부산 중구 중앙대로 2 1층", "부산 중구 중앙대로 2 지상1층"),
        ]
        for address, location in cases:
            for mention in ("테스트커피 서면점은", "테스트커피서면점에는", "테스트커피 서면점에서", "'테스트커피 서면점'"):
                with self.subTest(address=address, location=location, mention=mention):
                    row = self.row(address, f"{location} {mention} 좌석마다 콘센트가 있어요.")
                    self.assertTrue(matching_address(address, row.evidence))
                    self.assertEqual(assess_content(row)[0], "approve")

    def test_multiple_addresses_and_units_beyond_old_window_stay_held(self):
        cases = [
            ("부산 중구 중앙대로 2", "부산 중구 광복로 10에서 부산 중구 중앙대로 2로 이전"),
            ("서울 서초구 양재동 237", "서울 서초구 양재동 237에서 서울 서초구 서초동 12로 이전"),
            ("부산 중구 중앙대로 100 1층", "부산 중구 중앙대로 100\n" + " " * 45 + "2층"),
            ("부산 중구 중앙대로 100 1층", "부산 중구 중앙대로 100\nB2F"),
            ("부산 중구 중앙대로 100 지하 1층", "부산 중구 중앙대로 100\n1F"),
        ]
        for address, location in cases:
            with self.subTest(address=address, location=location):
                self.assertFalse(matching_address(address, location))
                self.assertEqual(assess_content(self.row(
                    address, f"{location} 테스트커피 서면점에는 콘센트가 있어요.",
                ))[0], "hold")

    def test_repeated_same_address_remains_approved(self):
        row = self.row(
            "부산 중구 중앙대로 2",
            "부산 중구 중앙대로 2 테스트커피 서면점에는 콘센트가 있어요. 주소: 부산 중구 중앙대로 2",
        )
        self.assertEqual(assess_content(row)[0], "approve")

    def test_moves_between_road_and_lot_forms_are_held(self):
        pairs = [
            ("부산 중구 중앙대로 2", "부산 해운대구 우동 1234"),
            ("서울 서초구 양재동 237", "서울 서초구 서초대로 100"),
        ]
        for old, new in pairs:
            for address in (old, new):
                with self.subTest(address=address, old=old, new=new):
                    row = self.row(address, f"테스트커피 서면점은 {old}에서 {new}로 이전했습니다. 새 매장에는 콘센트가 있어요.")
                    self.assertFalse(matching_address(address, row.evidence))
                    self.assertEqual(assess_content(row)[0], "hold")

    def test_branch_qualifiers_inside_punctuation_are_held(self):
        for suffix in ("(2호점)", "-2호점", "(별관)", "[2호점]", " / 2호점", "：별관", "(신관)"):
            for title_name, quote_name in (
                (f"테스트커피 서면점{suffix}", f"테스트커피 서면점{suffix}"),
                ("테스트커피 서면점", f"테스트커피 서면점{suffix}"),
                (f"테스트커피 서면점{suffix}", "테스트커피 서면점"),
            ):
                with self.subTest(suffix=suffix, title=title_name, quote=quote_name):
                    row = self.row("부산 중구 중앙대로 100", f"부산 중구 중앙대로 100 {quote_name}에는 콘센트가 있어요.", title=f"{title_name} 후기")
                    self.assertEqual(assess_content(row)[0], "hold")

    def test_address_labels_preserve_conflicting_and_matching_regions(self):
        for label in ("주소:", "[주소]:", "도로명주소:", "소재지:", "위치:"):
            for separator in (" ", ". ", "\n", "; "):
                for region, expected in (("대구 중구", "hold"), ("부산 중구", "approve")):
                    with self.subTest(label=label, separator=separator, region=region):
                        row = self.row(
                            "부산 중구 중앙대로 2",
                            f"{region}{separator}{label} 중앙대로 2 테스트커피 서면점에는 콘센트가 있어요.",
                            title="부산 테스트커피 서면점 후기",
                        )
                        self.assertEqual(assess_content(row)[0], expected)

    def test_separate_floor_and_room_fields_are_compared(self):
        for separator in (". ", "; ", "\n", " / "):
            for field, registered, same, other in (
                ("층수:", "1층", "1층", "2층"),
                ("층수:", "B1", "지하1층", "1층"),
                ("호수:", "101호", "101호", "102호"),
            ):
                for detail, expected in ((same, "approve"), (other, "hold")):
                    with self.subTest(separator=separator, field=field, detail=detail):
                        row = self.row(
                            f"부산 중구 중앙대로 2 {registered}",
                            f"부산 중구 중앙대로 2{separator}{field} {detail} 테스트커피 서면점에는 콘센트가 있어요.",
                        )
                        self.assertEqual(assess_content(row)[0], expected)

    def test_quantities_in_ordinary_prose_are_not_extra_addresses(self):
        for address in ("부산 중구 중앙대로 100", "서울 서초구 양재동 237"):
            for note in ("추가로 2잔 주문했어요.", "추가로 2 잔 주문했어요.", "우리가 2명 방문했어요.", "우리가 2 명 방문했어요.", "따로 3개 주문했어요."):
                with self.subTest(address=address, note=note):
                    row = self.row(address, f"{address} 테스트커피 서면점에는 콘센트가 있어요. {note}")
                    self.assertEqual(assess_content(row)[0], "approve")

    def test_normal_copulas_and_compound_particles_preserve_identity(self):
        for phrase in ("입니다.", "이에요.", "이네요.", "에서도", "에는", "으로는", "과는", "(후기)"):
            with self.subTest(phrase=phrase):
                row = self.row("부산 중구 중앙대로 100", f"부산 중구 중앙대로 100 여기는 테스트커피 서면점{phrase} 좌석마다 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "approve")
        # An allowed particle/copula prefix cannot excuse an extended name.
        for suffix in ("에서도2호점", "입니다별관"):
            with self.subTest(suffix=suffix):
                row = self.row("부산 중구 중앙대로 100", f"부산 중구 중앙대로 100 테스트커피 서면점{suffix}에는 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "hold")

    def test_facility_floor_is_not_the_store_address_floor(self):
        for clause in ("화장실은 2층에 있어요", "주차장은 지하 2층에 있어요", "엘리베이터는 3층까지 운행해요"):
            for actual_floor, expected in (("1층", "approve"), ("2층", "hold")):
                with self.subTest(clause=clause, actual_floor=actual_floor):
                    row = self.row(
                        "부산 중구 중앙대로 100 1층",
                        f"부산 중구 중앙대로 100 {actual_floor} 테스트커피 서면점에는 콘센트가 있고 {clause}.",
                    )
                    self.assertEqual(assess_content(row)[0], expected)

    def test_quantity_filter_does_not_swallow_business_names(self):
        for name in ("명가커피 서면점", "대가커피 서면점", "시간여행커피 서면점"):
            with self.subTest(name=name):
                row = self.row("부산 중구 중앙대로 100", f"부산 중구 중앙대로 100 {name}에는 콘센트가 있어요.", name=name)
                self.assertEqual(assess_content(row)[0], "approve")

    def test_registered_units_require_matching_address_details(self):
        for detail in ("", "층수: 미확인", "매장층수: 2층"):
            with self.subTest(detail=detail):
                row = self.row("부산 중구 중앙대로 2 1층", f"부산 중구 중앙대로 2 {detail} 테스트커피 서면점에는 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "hold")

    def test_registered_detail_syntax_cannot_remove_verification(self):
        cases = [
            ("1~2층", "3층", "hold"),
            ("제101호", "102호", "hold"),
            ("본관지하1층", "2층", "hold"),
            ("1~2층", "1층 2층", "approve"),
            ("1층 2층", "1~2층", "approve"),
            ("제101호", "101호", "approve"),
            ("본관지하1층", "본관 B1F", "approve"),
            ("1~999999층", "1층", "hold"),
            ("일층", "2층", "hold"),
            ("101~미정호", "102호", "hold"),
            ("A101호", "102호", "hold"),
        ]
        for registered, found, expected in cases:
            with self.subTest(registered=registered, found=found):
                row = self.row(
                    f"부산 중구 중앙대로 100 {registered}",
                    f"부산 중구 중앙대로 100 {found} 테스트커피 서면점에는 콘센트가 있어요.",
                )
                self.assertEqual(assess_content(row)[0], expected)

    def test_building_blocks_and_wings_are_identity_components(self):
        for registered, same, other in (
            ("A동 101호", "a동 제101호", "B동 101호"),
            ("101동 201호", "제101동 제201호", "102동 201호"),
            ("본관 1층", "본관1F", "별관 1층"),
            ("본관지하1층", "본관 B1", "별관 지하1층"),
            ("A동 본관 1층", "A동 본관 지상1층", "A동 별관 1층"),
            ("A1동 101호", "a1동 제101호", "A2동 101호"),
            ("B1동 101호", "b1동 제101호", "B1층 101호"),
            ("상가동 101호", "상가동 제101호", "업무동 101호"),
            ("동관 1층", "동관 지상1층", "서관 1층"),
        ):
            for found, expected in ((same, "approve"), (other, "hold"), ("", "hold")):
                with self.subTest(registered=registered, found=found):
                    row = self.row(
                        f"부산 중구 중앙대로 100 {registered}",
                        f"부산 중구 중앙대로 100 {found} 테스트커피 서면점에는 콘센트가 있어요.",
                    )
                    self.assertEqual(assess_content(row)[0], expected)

    def test_verified_details_allow_abbreviations_but_never_conflicts(self):
        base = "부산 중구 중앙대로 100"
        for detail in ("1층", "101호", "A동 본관 1층 101호"):
            verified = f"{base} {detail} 테스트커피 서면점에는 콘센트가 있어요."
            for prose in (f"{verified} 주소: {base}", f"주소: {base}. {verified}"):
                with self.subTest(detail=detail, prose=prose):
                    self.assertEqual(assess_content(self.row(f"{base} {detail}", prose))[0], "approve")
        for partial in ("2층", "102호", "B동", "별관", "층수: 미확인", "1층 층수: 미확인", "일층"):
            for prefix, suffix in ((f"{base} {partial}. ", ""), ("", f" 주소: {base} {partial}")):
                with self.subTest(partial=partial, prefix=prefix):
                    row = self.row(
                        f"{base} A동 본관 1층 101호",
                        f"{prefix}{base} A동 본관 1층 101호 테스트커피 서면점에는 콘센트가 있어요.{suffix}",
                    )
                    self.assertEqual(assess_content(row)[0], "hold")
        # Details from different incomplete mentions must not be assembled
        # into a supposedly verified complete address.
        row = self.row(f"{base} 1층 101호", f"{base} 1층 테스트커피 서면점에는 콘센트가 있어요. 주소: {base} 101호")
        self.assertEqual(assess_content(row)[0], "hold")

    def test_equivalent_details_after_phone_or_exact_place_name(self):
        for registered, found in (
            ("101호", "제101호 테스트커피 서면점"),
            ("1층", "0507-1234-5678 1층 테스트커피 서면점"),
            ("1층", "전화: 02-123-4567 / 1층 테스트커피 서면점"),
            ("1층", "테스트커피 서면점 1층"),
            ("1층", "테스트커피서면점 0507-1234-5678 1층"),
        ):
            with self.subTest(registered=registered, found=found):
                row = self.row(f"부산 중구 중앙대로 100 {registered}", f"부산 중구 중앙대로 100 {found}에는 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "approve")
        for found in (
            "테스트커피 서면점 2층", "0507-1234-5678 2층 테스트커피 서면점",
            "테스트커피 서면점 화장실은 1층이고 매장에는",
            "테스트커피 서면점 주차장은 1층이고 매장에는",
            "다른커피 1층 테스트커피 서면점", "테스트커피 서면점",
        ):
            with self.subTest(found=found):
                row = self.row("부산 중구 중앙대로 100 1층", f"부산 중구 중앙대로 100 {found} 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "hold")

    def test_ordinal_branch_names_are_not_the_registered_branch(self):
        for suffix in (" 제2호점", "제2호점", " (제 2 호점)", "[제02호점]", " / 제2호점"):
            other = f"테스트커피 서면점{suffix}"
            for title, quote in ((other, other), (other, "테스트커피 서면점"), ("테스트커피 서면점", other)):
                with self.subTest(suffix=suffix, title=title, quote=quote):
                    row = self.row("부산 중구 중앙대로 100", f"부산 중구 중앙대로 100 {quote}에는 콘센트가 있어요.", title=f"{title} 후기")
                    self.assertEqual(assess_content(row)[0], "hold")

    def test_visit_counts_do_not_hide_real_numbered_addresses(self):
        for note in ("추가로 2번 방문했어요.", "추가로 2 번 방문했어요.", "추가로 2번씩 방문했어요."):
            with self.subTest(note=note):
                row = self.row("부산 중구 중앙대로 100", f"부산 중구 중앙대로 100 테스트커피 서면점에는 콘센트가 있어요. {note}")
                self.assertEqual(assess_content(row)[0], "approve")
        for other in ("부산 중구 추가로 2번지", "부산 중구 추가로2번길 5", "부산 중구 중앙대로 101"):
            with self.subTest(other=other):
                row = self.row("부산 중구 중앙대로 100", f"부산 중구 중앙대로 100에서 {other}로 이전한 테스트커피 서면점에는 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "hold")

    def test_unparsed_registered_floor_markers_never_waive_verification(self):
        for registered in ("중1층", "옥탑층", "다락층", "복층"):
            for found in ("2층", "", registered):
                with self.subTest(registered=registered, found=found):
                    row = self.row(f"부산 중구 중앙대로 100 {registered}", f"부산 중구 중앙대로 100 {found} 테스트커피 서면점에는 콘센트가 있어요.")
                    self.assertEqual(assess_content(row)[0], "hold")

    def test_named_buildings_and_blocks_are_preserved(self):
        for registered, same, different in (
            ("교육동 101호", "교육 동 제101호", "판매동 101호"),
            ("별동 1층", "별동 지상1층", "본동 1층"),
            ("알파빌딩 1층", "알파 빌딩 1F", "베타빌딩 1층"),
            ("알파타워 101호", "알파 타워 101호", "베타타워 101호"),
            ("교육관 1층", "교육 관 1층", "연구관 1층"),
        ):
            for found, expected in ((same, "approve"), (different, "hold"), ("", "hold")):
                with self.subTest(registered=registered, found=found):
                    row = self.row(f"부산 중구 중앙대로 100 {registered}", f"부산 중구 중앙대로 100 {found} 테스트커피 서면점에는 콘센트가 있어요.")
                    self.assertEqual(assess_content(row)[0], expected)
        for found, expected in (("테스트알파빌딩", "approve"), ("테스트베타빌딩", "hold")):
            row = self.row("부산 중구 중앙대로 100 테스트알파빌딩 1층", f"부산 중구 중앙대로 100 {found} 1층 테스트알파빌딩에는 콘센트가 있어요.", name="테스트알파빌딩")
            self.assertEqual(assess_content(row)[0], expected)
        row = self.row("부산 중구 중앙대로 100 알파빌딩 1층", "부산 중구 중앙대로 100 알파빌딩 1층 테스트문화센터에는 콘센트가 있어요.", name="테스트문화센터")
        self.assertEqual(assess_content(row)[0], "approve")

    def test_details_after_name_particles_have_consistent_attribution(self):
        base = "부산 중구 중앙대로 100"
        for detail, other in (("1층", "2층"), ("101호", "102호")):
            for particle in ("은", "는", "이", "가", "에는"):
                for found, expected in ((detail, "approve"), (other, "hold"), ("", "hold")):
                    with self.subTest(detail=detail, particle=particle, found=found):
                        prose = f"{base} 테스트커피 서면점{particle} {found}에 있고 콘센트가 있어요."
                        self.assertEqual(assess_content(self.row(f"{base} {detail}", prose))[0], expected)
                conflict = f"{base} {detail} 테스트커피 서면점에는 콘센트가 있어요. 주소: {base} 테스트커피 서면점{particle} {other}에 있습니다."
                self.assertEqual(assess_content(self.row(f"{base} {detail}", conflict))[0], "hold")
        for facility in ("화장실은 2층", "주차장은 지하2층"):
            prose = f"{base} 1층 테스트커피 서면점에는 콘센트가 있어요. 주소: {base} 테스트커피 서면점은 {facility}에 있어요."
            self.assertEqual(assess_content(self.row(f"{base} 1층", prose))[0], "approve")

    def test_wing_suffixes_in_title_and_separate_prose_are_held(self):
        base = "부산 중구 중앙대로 100"
        for wing in ("구관", "동관", "서관", "남관", "북관"):
            for title_name, quote_name in (
                (f"테스트커피 서면점 {wing}", "테스트커피 서면점"),
                ("테스트커피 서면점", f"테스트커피 서면점 {wing}"),
                (f"테스트커피 서면점 {wing}", f"테스트커피 서면점 {wing}"),
            ):
                with self.subTest(wing=wing, title=title_name, quote=quote_name):
                    row = self.row(base, f"{base} 매장 안내입니다. {quote_name}에는 콘센트가 있어요.", title=f"{title_name} 후기")
                    self.assertEqual(assess_content(row)[0], "hold")

    def test_range_abbreviations_require_a_complete_verified_mention(self):
        base = "부산 중구 중앙대로 100"
        for detail, part, outside in (("1~2층", "1층", "3층"), ("101~102호", "101호", "103호")):
            complete = f"{base} {detail} 테스트커피 서면점에는 콘센트가 있어요."
            for abbreviated in (part, ""):
                for prose in (f"{complete} 주소: {base} {abbreviated}", f"주소: {base} {abbreviated}. {complete}"):
                    with self.subTest(detail=detail, prose=prose):
                        self.assertEqual(assess_content(self.row(f"{base} {detail}", prose))[0], "approve")
            for prose in (f"{base} {part} 테스트커피 서면점에는 콘센트가 있어요.", f"{complete} 주소: {base} {outside}"):
                self.assertEqual(assess_content(self.row(f"{base} {detail}", prose))[0], "hold")

    def test_range_endpoint_units_are_equivalent_without_widening_ranges(self):
        base = "부산 중구 중앙대로 100"
        for left, right in (
            ("1층~2층", "1~2층"), ("101호~102호", "101~102호"),
            ("1F~2F", "1층 2층"), ("지하1층~지하2층", "B1F B2F"),
        ):
            for registered, found in ((left, right), (right, left)):
                with self.subTest(registered=registered, found=found):
                    self.assertEqual(assess_content(self.row(f"{base} {registered}", f"{base} {found} 테스트커피 서면점에는 콘센트가 있어요."))[0], "approve")
        for unsupported in ("2층~1층", "1층~2호", "1층~999999층", "지하1층~2층"):
            with self.subTest(unsupported=unsupported):
                self.assertEqual(assess_content(self.row(f"{base} {unsupported}", f"{base} 1층 테스트커피 서면점에는 콘센트가 있어요."))[0], "hold")

    def test_unparsed_range_continuations_never_verify_only_the_first_value(self):
        base = "부산 중구 중앙대로 100"
        for registered, found in (
            ("B1~B2", "B1"), ("B1", "B1~B2"), ("B1~B2", "B1~B2"),
            ("101호", "101호~103"), ("1층", "1층 및 2층"), ("1층", "1층~"),
        ):
            with self.subTest(registered=registered, found=found):
                quote = f"{base} {found} 테스트커피 서면점에는 콘센트가 있어요."
                self.assertEqual(assess_content(self.row(f"{base} {registered}", quote))[0], "hold")
        quote = f"{base} 1층 및 2인석 안내. 테스트커피 서면점에는 콘센트가 있어요."
        self.assertEqual(assess_content(self.row(f"{base} 1층", quote))[0], "approve")
        quote = f"{base} 1층 - 테스트커피 서면점에는 콘센트가 있어요."
        self.assertEqual(assess_content(self.row(f"{base} 1층", quote))[0], "approve")

    def test_floor_and_room_words_are_not_road_building_numbers(self):
        for number in ("100층입니다.", "100층인", "100호실", "100 층입니다.", "100 호실"):
            with self.subTest(number=number):
                row = self.row("부산 중구 중앙대로 100", f"부산 중구 중앙대로 {number} 테스트커피 서면점에는 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "hold")
        row = self.row("부산 중구 중앙대로 100", "부산 중구 중앙대로 100 호호커피 서면점에는 콘센트가 있어요.", name="호호커피 서면점")
        self.assertEqual(assess_content(row)[0], "approve")

    def test_title_building_identity_must_agree_with_registered_address(self):
        base = "부산 중구 중앙대로 100"
        for registered, same, different in (
            ("A동 101호", "A동", "B동"),
            ("알파빌딩 1층", "알파빌딩", "베타빌딩"),
            ("교육동 101호", "교육동", "판매동"),
        ):
            for title_detail, expected in ((same, "approve"), (different, "hold")):
                with self.subTest(registered=registered, title_detail=title_detail):
                    row = self.row(f"{base} {registered}", f"{base} {registered} 테스트커피 서면점에는 콘센트가 있어요.", title=f"테스트커피 서면점 {title_detail} 후기")
                    self.assertEqual(assess_content(row)[0], expected)
        row = self.row(f"{base} A동 101호", f"{base} A동 101호 테스트커피 서면점에는 콘센트가 있어요.", title="테스트커피 서면점 감동 후기")
        self.assertEqual(assess_content(row)[0], "approve")
        for floor, expected in (("1층", "approve"), ("2층", "hold"), ("층수: 미확인", "hold"), ("호수: 미확인", "hold")):
            row = self.row(f"{base} 1층", f"{base} 1층 테스트커피 서면점에는 콘센트가 있어요.", title=f"테스트커피 서면점 {floor} 후기")
            self.assertEqual(assess_content(row)[0], expected)

    def test_punctuated_names_preserve_details_and_explicit_conflicts(self):
        base = "부산 중구 중앙대로 100"
        for name in ("테스트커피·서면점", "'테스트커피 서면점'", '"테스트커피 서면점"', "테스트커피 (서면점)"):
            with self.subTest(name=name):
                quote = f"{base} {name}은 1층에 있고 콘센트가 있어요."
                self.assertEqual(assess_content(self.row(f"{base} 1층", quote))[0], "approve")
                quote = f"{base} 2층 테스트커피 서면점에는 콘센트가 있어요. 주소: {base} {name}은 1층에 있습니다."
                self.assertEqual(assess_content(self.row(f"{base} 2층", quote))[0], "hold")

    def test_complete_building_names_do_not_stop_at_an_embedded_suffix(self):
        base = "부산 중구 중앙대로 100"
        for building in ("신동아빌딩", "강동타워", "중앙상가빌딩"):
            for found, expected in ((building, "approve"), (f"다른{building}", "hold")):
                with self.subTest(building=building, found=found):
                    row = self.row(f"{base} {building} 1층", f"{base} {found} 1층 테스트커피 서면점에는 콘센트가 있어요.")
                    self.assertEqual(assess_content(row)[0], expected)

    def test_postal_neighborhoods_are_optional_but_explicit_conflicts_are_not(self):
        base = "부산 중구 중앙대로 100"
        registered = f"{base} (중앙동) 1층"
        for location, expected in (
            ("부산 중구 중앙동 중앙대로 100 1층", "approve"),
            # No typed administrative prefix: same spelling is not proof
            # that a parenthesized dong is optional postal metadata.
            (f"{base} 1층", "hold"), (f"{base} (중앙동) 1층", "hold"),
            ("부산 중구 대청동 중앙대로 100 1층", "hold"),
            (f"{base} (대청동) 1층", "hold"), (f"{base} (중앙동)", "hold"),
        ):
            with self.subTest(location=location):
                self.assertEqual(assess_content(self.row(registered, f"{location} 테스트커피 서면점에는 콘센트가 있어요."))[0], expected)
        for registered_detail, found in (("(A동) 101호", "(B동) 101호"), ("(A동) 101호", "101호"), ("(교육동 101호)", "(판매동 101호)")):
            with self.subTest(registered_detail=registered_detail, found=found):
                row = self.row(f"{base} {registered_detail}", f"{base} {found} 테스트커피 서면점에는 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "hold")

    def test_ambiguous_dong_requires_explicit_type_context(self):
        base = "부산 중구 중앙대로 100"
        for registered, found in (
            ("(교육동) 101호", "판매동 101호"), ("(상가동) 1층", "업무동 1층"),
            ("(중앙동) 1층", "1층"), ("(중앙동) 1층", "(중앙동) 1층"),
        ):
            with self.subTest(registered=registered, found=found):
                row = self.row(f"{base} {registered}", f"{base} {found} 테스트커피 서면점에는 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "hold")
        for registered, found in (("교육동 101호", "(교육동) 101호"), ("상가동 1층", "(상가동) 1층")):
            with self.subTest(registered=registered, found=found):
                row = self.row(f"{base} {registered}", f"{base} {found} 테스트커피 서면점에는 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "approve")
        address = "부산 중구 중앙동 중앙대로 100 중앙동 101호"
        row = self.row(address, f"{address} 테스트커피 서면점에는 콘센트가 있어요.", title="테스트커피 서면점 후기 (중앙동)")
        self.assertEqual(assess_content(row)[0], "hold")

    def test_title_unparsed_state_vetoes_partial_detail_matches(self):
        base = "부산 중구 중앙대로 100"
        for registered, title_detail in (("1층", "1층~"), ("B1", "B1~B2"), ("1층", "1층 및 2층")):
            with self.subTest(registered=registered, title_detail=title_detail):
                row = self.row(f"{base} {registered}", f"{base} {registered} 테스트커피 서면점에는 콘센트가 있어요.", title=f"테스트커피 서면점 {title_detail} 후기")
                self.assertEqual(assess_content(row)[0], "hold")

    def test_title_details_are_compared_before_and_after_the_place_name(self):
        base = "부산 중구 중앙대로 100"
        for registered, same, other in (("A동 101호", "A동", "B동"), ("알파빌딩 1층", "알파빌딩", "베타빌딩")):
            for detail, expected in ((same, "approve"), (other, "hold")):
                for title in (f"{detail} 테스트커피 서면점 후기", f"테스트커피 서면점 후기 ({detail})"):
                    with self.subTest(registered=registered, title=title):
                        row = self.row(f"{base} {registered}", f"{base} {registered} 테스트커피 서면점에는 콘센트가 있어요.", title=title)
                        self.assertEqual(assess_content(row)[0], expected)

    def test_korean_block_letters_are_not_exempted_as_narrative_words(self):
        base = "부산 중구 중앙대로 100"
        for registered, title_detail, expected in (
            ("A동 101호", "가동", "hold"), ("가동 101호", "나동", "hold"),
            ("가동 101호", "가동", "approve"), ("가동 101호", "감동", "approve"),
            ("A동 101호", "감동", "approve"), ("A동 101호", "가동 101호", "hold"),
            ("A동 101호", "자동", "hold"),
        ):
            with self.subTest(registered=registered, title_detail=title_detail):
                row = self.row(f"{base} {registered}", f"{base} {registered} 테스트커피 서면점에는 콘센트가 있어요.", title=f"테스트커피 서면점 {title_detail} 후기")
                self.assertEqual(assess_content(row)[0], expected)

    def test_unparsed_korean_ranges_are_not_single_floors(self):
        base = "부산 중구 중앙대로 100"
        for registered, found in (("1층", "1층부터 2층까지"), ("1층부터2층까지", "1층"), ("1층", "1층 내지 2층")):
            with self.subTest(registered=registered, found=found):
                row = self.row(f"{base} {registered}", f"{base} {found} 테스트커피 서면점에는 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "hold")
        row = self.row(f"{base} 1층", f"{base} 1층에서 테스트커피 서면점에는 콘센트가 있어요.")
        self.assertEqual(assess_content(row)[0], "approve")

    def test_known_wing_names_share_a_canonical_spelling(self):
        base = "부산 중구 중앙대로 100"
        for registered, found in (("본관 1층", "본 관 1층"), ("별 관 1층", "별관 1층"), ("교육관 1층", "교육 관 1층")):
            with self.subTest(registered=registered, found=found):
                row = self.row(f"{base} {registered}", f"{base} {found} 테스트커피 서면점에는 콘센트가 있어요.")
                self.assertEqual(assess_content(row)[0], "approve")

    def test_registered_wing_qualifier_is_allowed_only_when_it_matches(self):
        base = "부산 중구 중앙대로 100"
        for wing, expected in (("본관", "approve"), ("본 관", "approve"), ("별관", "hold")):
            with self.subTest(wing=wing):
                row = self.row(f"{base} 본관 1층", f"{base} 본관 1층 테스트커피 서면점에는 콘센트가 있어요.", title=f"테스트커피 서면점 {wing} 후기")
                self.assertEqual(assess_content(row)[0], expected)
        row = self.row(f"{base} 1층", f"{base} 1층 테스트커피 서면점에는 콘센트가 있어요.", title="테스트커피 서면점 본관 후기")
        self.assertEqual(assess_content(row)[0], "hold")
        for extended in ("테스트커피 서면점(본관)2호점", "테스트커피 서면점 본관 분점"):
            row = self.row(f"{base} 본관 1층", f"{base} 본관 1층 {extended}에는 콘센트가 있어요.")
            self.assertEqual(assess_content(row)[0], "hold")

    def test_title_building_particles_preserve_identity_and_conflicts(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for registered, same, other in (("본관 1층", "본관", "별관"), ("A동 101호", "A동", "B동"), ("알파빌딩 1층", "알파빌딩", "베타빌딩"), ("가동 101호", "가동", "나동")):
            for ending in ("에서", "의", "에는"):
                for detail, expected in ((same, "approve"), (other, "hold")):
                    for title in (f"{detail}{ending} {name} 후기", f"{name} 후기 {detail}{ending} 방문"):
                        with self.subTest(registered=registered, title=title):
                            row = self.row(f"{base} {registered}", f"{base} {registered} {name}에는 콘센트가 있어요.", title=title)
                            self.assertEqual(assess_content(row)[0], expected)

    def test_title_unsupported_floor_markers_stay_unparsed(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for detail in ("옥탑층", "미확인층", "중1층", "다락층", "층수: 미확인", "1층~", "미확인층 화장실"):
            with self.subTest(detail=detail):
                row = self.row(f"{base} 1층", f"{base} 1층 {name}에는 콘센트가 있어요.", title=f"{name} {detail} 후기")
                self.assertEqual(assess_content(row)[0], "hold")

    def test_title_address_numbers_are_compared_without_requiring_title_units(self):
        name = "테스트커피 서면점"
        for registered, title_address, expected in (
            ("부산 중구 중앙대로 100 1층", "부산 중구 중앙대로 100", "approve"),
            ("부산 중구 중앙대로 100 1층", "중앙대로 100", "approve"),
            ("부산 중구 중앙대로 100 1층", "부산 중구 중앙대로 101", "hold"),
            ("부산 중구 중앙대로 100 1층", "부산 중구 중앙대로 100-1", "hold"),
            ("부산 중구 중앙대로 100 1층", "부산 동구 중앙대로 100", "hold"),
            ("부산 중구 중앙대로 100 1층", "부산 중구 다른로 100", "hold"),
            ("부산 중구 중앙동 237 101호", "부산 중구 중앙동 237-0", "approve"),
            ("부산 중구 중앙동 237 101호", "부산 중구 중앙동 238", "hold"),
        ):
            with self.subTest(registered=registered, title_address=title_address):
                row = self.row(registered, f"{registered} {name}에는 콘센트가 있어요.", title=f"{title_address} {name} 후기")
                self.assertEqual(assess_content(row)[0], expected)

        row = self.row("부산 중구 중앙대로 100 1층", f"부산 중구 중앙대로 100 1층 {name}에는 콘센트가 있어요.", title=f"서울 중구 중앙대로 100 {name} 후기")
        self.assertEqual(assess_content(row), ("reject", "title_city_mismatch"))

    def test_bracket_variants_never_resolve_ambiguous_dong_by_themselves(self):
        name, base = "테스트커피 서면점", "부산 중구 중앙대로 100"
        both = "부산 중구 중앙동 중앙대로 100 중앙동 101호"
        for bracket in ("(중앙동)", "[중앙동]", "{중앙동}", "((중앙동))", "[{중앙동}]", "( [중앙동] )"):
            for in_title in (True, False):
                with self.subTest(bracket=bracket, in_title=in_title):
                    quote = both if in_title else f"부산 중구 중앙동 중앙대로 100 {bracket} 101호"
                    title = f"{name} 후기 {bracket}" if in_title else f"{name} 후기"
                    self.assertEqual(assess_content(self.row(both, f"{quote} {name}에는 콘센트가 있어요.", title=title))[0], "hold")
            ambiguous = f"{base} {bracket} 101호"
            self.assertEqual(assess_content(self.row(ambiguous, f"{ambiguous} {name}에는 콘센트가 있어요."))[0], "hold")
        for bracket in ("[교육동]", "{교육동}", "((교육동))"):
            self.assertEqual(assess_content(self.row(f"{base} 교육동 101호", f"{base} {bracket} 101호 {name}에는 콘센트가 있어요."))[0], "approve")

    def test_restroom_floor_in_title_is_not_the_store_floor(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for detail, expected in (("2층 화장실 이용 안내", "approve"), ("화장실은 2층", "approve"), ("2층에 있는 화장실 이용 안내", "approve"), ("화장실은 2층, 매장은 3층", "hold"), ("2층 화장실, B동 방문", "hold"), ("2층 화장실, 102호 후기", "hold"), ("층수: 2층 화장실", "hold")):
            with self.subTest(detail=detail):
                row = self.row(f"{base} A동 1층 101호", f"{base} A동 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} {detail}")
                self.assertEqual(assess_content(row)[0], expected)

    def test_subway_line_is_not_a_room_number(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for detail, expected in (("1호선 역세권", "approve"), ("101호실 후기", "approve"), ("102호실 후기", "hold"), ("1호선 102호 후기", "hold")):
            with self.subTest(detail=detail):
                row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} {detail}")
                self.assertEqual(assess_content(row)[0], expected)
        row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 1호선 역세권인 {name}에는 콘센트가 있어요.")
        self.assertEqual(assess_content(row)[0], "approve")

    def test_unicode_brackets_preserve_city_and_building_conflicts(self):
        name = "테스트커피 서면점"
        for opening, closing in (("(", ")"), ("（", "）"), ("【", "】"), ("〔", "〕"), ("「", "」")):
            for city, expected in (("부산", "approve"), ("서울", "reject")):
                with self.subTest(opening=opening, city=city):
                    row = self.row("부산 중구 중앙대로 100 1층", f"부산 중구 중앙대로 100 1층 {name}에는 콘센트가 있어요.", title=f"{opening}{city} 중구 중앙대로 100{closing} {name} 후기")
                    self.assertEqual(assess_content(row)[0], expected)
            row = self.row("부산 중구 중앙대로 100 A동 101호", f"부산 중구 중앙대로 100 A동 101호 {name}에는 콘센트가 있어요.", title=f"{name} 후기 {opening}B동{closing}")
            self.assertEqual(assess_content(row)[0], "hold")

    def test_title_unparsed_floor_endings_and_field_particles_remain_held(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for detail in ("옥탑층이에요", "옥탑층에서", "미확인층에", "중1층입니다", "층수는 미확인", "층수는미확인", "호수는 미확인", "미확인층의 화장실"):
            with self.subTest(detail=detail):
                row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} {detail} 후기")
                self.assertEqual(assess_content(row)[0], "hold")

    def test_compact_store_floor_description_is_never_discarded(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for detail, expected in (("매장은1층", "approve"), ("매장은3층", "hold"), ("매장은미확인층", "hold"), ("가게는1층", "approve"), ("매장은1층 102호", "hold"), ("층수는1층", "approve")):
            with self.subTest(detail=detail):
                row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} {detail} 후기")
                self.assertEqual(assess_content(row)[0], expected)

    def test_dong_particles_preserve_ambiguity_inside_every_bracket(self):
        name = "테스트커피 서면점"
        registered = "부산 중구 중앙동 중앙대로 100 중앙동 101호"
        for opening, closing in (("(", ")"), ("[", "]"), ("（", "）"), ("【", "】")):
            for ending in ("", "의", "에서"):
                with self.subTest(opening=opening, ending=ending):
                    row = self.row(registered, f"{registered} {name}에는 콘센트가 있어요.", title=f"{name} 후기 {opening}중앙동{ending}{closing}")
                    self.assertEqual(assess_content(row)[0], "hold")
        base = "부산 중구 중앙대로 100"
        for detail, expected in (("[교육동의]", "approve"), ("[판매동의]", "hold")):
            self.assertEqual(assess_content(self.row(f"{base} 교육동 101호", f"{base} 교육동 101호 {name}에는 콘센트가 있어요.", title=f"{name} {detail} 후기"))[0], expected)

    def test_typed_neighborhood_in_title_is_not_a_building_block(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for title, expected in ((f"부산 중구 중앙동 중앙대로 100 {name} 후기", "approve"), (f"부산 중구 대청동 중앙대로 100 {name} 후기", "hold"), (f"부산 중구 중앙동 중앙대로 100 {name} 후기 (B동)", "hold"), (f"{name} 후기 (중앙동)", "approve")):
            with self.subTest(title=title):
                row = self.row(f"{base} 1층", f"부산 중구 중앙동 중앙대로 100 1층 {name}에는 콘센트가 있어요.", title=title)
                self.assertEqual(assess_content(row)[0], expected)

    def test_restroom_equivalent_floor_ranges_do_not_verify_store_details(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for detail, expected in (("2층의 화장실", "approve"), ("화장실 위치: 2층", "approve"), ("1~2층 화장실", "approve"), ("1층~2층 화장실", "approve"), ("화장실은1~2층", "approve"), ("화장실은2층", "approve"), ("B1~B2 화장실", "hold"), ("1층부터 2층까지 화장실", "hold"), ("화장실은 1~2층, 매장은3층", "hold"), ("1~2층 화장실, 102호", "hold")):
            with self.subTest(detail=detail):
                row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} {detail} 안내")
                self.assertEqual(assess_content(row)[0], expected)
        row = self.row(f"{base} 1층 101호", f"{base} {name}에는 콘센트가 있어요.", title=f"{name} 1층 101호 화장실 안내")
        self.assertEqual(assess_content(row)[0], "hold")

    def test_rail_after_conjunction_is_not_an_unparsed_room_range(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for conjunction in ("및", "그리고"):
            for in_title in (True, False):
                with self.subTest(conjunction=conjunction, in_title=in_title):
                    detail = f"101호 {conjunction} 1호선 역세권"
                    quote = f"{base} 1층 101호" if in_title else f"{base} 1층 {detail}인"
                    title = f"{name} {detail} 후기" if in_title else f"{name} 후기"
                    self.assertEqual(assess_content(self.row(f"{base} 1층 101호", f"{quote} {name}에는 콘센트가 있어요.", title=title))[0], "approve")
        row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} 101호 및 102호 후기")
        self.assertEqual(assess_content(row)[0], "hold")

    def test_restroom_mask_preserves_unparsed_range_continuations(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for detail, expected in (("화장실은2층부터", "hold"), ("화장실은 2층 내지", "hold"), ("화장실은2층부터미확인", "hold"), ("화장실은1~2층부터", "hold"), ("화장실은 2층~", "hold"), ("화장실은1~2층", "approve"), ("화장실은2층, 매장은3층", "hold")):
            with self.subTest(detail=detail):
                row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} {detail} 후기")
                self.assertEqual(assess_content(row)[0], expected)

    def test_other_ordinal_branches_never_borrow_the_registered_identity(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 2호점"
        for conjunction in ("및", "그리고"):
            for qualifier, expected in (("1호점", "hold"), ("2호점", "approve"), ("제02호점", "approve"), ("1호선", "approve")):
                with self.subTest(conjunction=conjunction, qualifier=qualifier):
                    row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 {conjunction} {qualifier} {name}에는 콘센트가 있어요.", name=name)
                    self.assertEqual(assess_content(row)[0], expected)
        row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 {name}에는 콘센트가 있어요.", name=name, title=f"{name} 그리고 1호점 후기")
        self.assertEqual(assess_content(row)[0], "hold")

    def test_exact_place_names_precede_generic_store_subjects(self):
        base = "부산 중구 중앙대로 100"
        for name in ("매장이야기 서면점", "가게이야기 서면점", "점포가든 서면점", "테스트커피 서면점"):
            for floor, expected in (("1층", "approve"), ("2층", "hold")):
                with self.subTest(name=name, floor=floor):
                    row = self.row(f"{base} 1층", f"{base} {name} {floor} {name}에는 콘센트가 있어요.", name=name)
                    self.assertEqual(assess_content(row)[0], expected)

    def test_registered_wing_accepts_attached_units_but_not_branch_extensions(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for detail, expected in (("본관1층", "approve"), ("본 관1층", "approve"), ("본관2층", "hold"), ("별관1층", "hold"), ("본관1호점", "hold")):
            with self.subTest(detail=detail):
                row = self.row(f"{base} 본관 1층", f"{base} 본관 1층 {name}에는 콘센트가 있어요.", title=f"{name} {detail} 후기")
                self.assertEqual(assess_content(row)[0], expected)

    def test_building_particles_share_the_attached_unit_boundary(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for detail, expected in (("A동은1층", "approve"), ("A동의1층", "approve"), ("A동은3층", "hold"), ("B동은1층", "hold"), ("A동은1층 102호", "hold")):
            with self.subTest(detail=detail):
                row = self.row(f"{base} A동 1층 101호", f"{base} A동 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} {detail} 후기")
                self.assertEqual(assess_content(row)[0], expected)

    def test_restroom_floor_attached_to_a_block_keeps_the_block_identity(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for block in ("A동", "교육동", "본관"):
            with self.subTest(block=block):
                row = self.row(f"{base} {block} 1층 101호", f"{base} {block} 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} {block}2층 화장실 후기")
                self.assertEqual(assess_content(row)[0], "approve")
        for detail in ("B동2층 화장실", "옥탑2층 화장실", "A동2층 화장실, 102호"):
            with self.subTest(detail=detail):
                row = self.row(f"{base} A동 1층 101호", f"{base} A동 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} {detail} 후기")
                self.assertEqual(assess_content(row)[0], "hold")

    def test_lake_prose_is_not_an_unknown_room_field(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for detail, expected in (("호수는 아름다운 풍경", "approve"), ("호수는 산책하기 좋은 곳", "approve"), ("호수는101호", "approve"), ("호수는102호", "hold"), ("호수는미확인", "hold"), ("호수는 부정확", "hold"), ("호수: 미확인", "hold")):
            with self.subTest(detail=detail):
                row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} {detail} 후기")
                self.assertEqual(assess_content(row)[0], expected)

    def test_attached_unit_must_end_before_it_can_verify_a_place_name(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for suffix, registered, expected in (("1층점", "1층", "hold"), ("1층분점", "1층", "hold"), ("101호실점", "101호", "hold"), ("1F점", "1층", "hold"), ("1층", "1층", "approve"), ("1F", "1층", "approve"), ("101호실", "101호", "approve")):
            for in_title in (True, False):
                with self.subTest(suffix=suffix, in_title=in_title):
                    extended = f"{name}{suffix}"
                    quote = f"{base} {registered} {name}" if in_title else f"{base} {extended}"
                    title = f"{extended} 후기" if in_title else f"{name} 후기"
                    row = self.row(f"{base} {registered}", f"{quote}에는 콘센트가 있어요.", title=title)
                    self.assertEqual(assess_content(row)[0], expected)

    def test_unknown_detail_values_share_the_candidate_and_field_boundary(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for field in ("층수", "호수"):
            for value in ("미상", "미기재", "부정확", "없음", "미확인"):
                for gap in ("", " "):
                    with self.subTest(field=field, value=value, gap=gap):
                        row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} {field}는{gap}{value} 후기")
                        self.assertEqual(assess_content(row)[0], "hold")
        row = self.row(f"{base} 1층 101호", f"{base} 1층 101호 {name}에는 콘센트가 있어요.", title=f"{name} 호수는 아름다운 풍경 후기")
        self.assertEqual(assess_content(row)[0], "approve")

    def test_range_connectors_cannot_depend_on_a_known_endpoint_word(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 서면점"
        for value in ("미상", "미기재", "부정확", "미확인", "알수없음"):
            for in_title in (True, False):
                with self.subTest(value=value, in_title=in_title):
                    quote = f"{base} 2층" if in_title else f"{base} 2층내지{value}"
                    title = f"{name} 화장실은2층부터{value} 후기" if in_title else f"{name} 후기"
                    self.assertEqual(assess_content(self.row(f"{base} 2층", f"{quote} {name}에는 콘센트가 있어요.", title=title))[0], "hold")
        name = "부터커피 서면점"
        row = self.row(f"{base} 1층", f"{base} 1층 {name}에는 콘센트가 있어요.", name=name)
        self.assertEqual(assess_content(row)[0], "approve")

    def test_same_ordinal_branch_repetition_is_equal_in_title_and_body(self):
        base, name = "부산 중구 중앙대로 100", "테스트커피 2호점"
        for qualifier, expected in (("2호점", "approve"), ("제02호점", "approve"), ("1호점", "hold")):
            for in_title in (True, False):
                with self.subTest(qualifier=qualifier, in_title=in_title):
                    quote = f"{base} 1층 101호" + ("" if in_title else f" {qualifier}")
                    title = f"{name} 안내 ({qualifier}) 후기" if in_title else f"{name} 후기"
                    row = self.row(f"{base} 1층 101호", f"{quote} {name}에는 콘센트가 있어요.", name=name, title=title)
                    self.assertEqual(assess_content(row)[0], expected)
