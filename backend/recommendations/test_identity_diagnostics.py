from types import SimpleNamespace

from django.test import SimpleTestCase

from recommendations.services.identity_diagnostics import classify_rejected_result


class IdentityDiagnosticsTests(SimpleTestCase):
    def place(self, name="고더커피 수영점", address="부산 수영구 무학로9번길 50"):
        return SimpleNamespace(name=name, address=address)

    def test_classifies_wrong_branch(self):
        result = classify_rejected_result(self.place(), "고더커피 해운대점 분위기 좋은 카페")
        self.assertEqual(result["reason"], "BRANCH_NAME_MISMATCH")

    def test_classifies_exact_name_without_location_as_threshold_issue(self):
        result = classify_rejected_result(
            self.place(name="강변둥지공원", address="부산광역시 북구 화명동 188-2"),
            "강변둥지공원 산책 후기",
        )
        self.assertEqual(result["reason"], "IDENTITY_THRESHOLD")

    def test_classifies_unrelated_result(self):
        result = classify_rejected_result(self.place(), "서울 전혀 다른 카페 후기")
        self.assertEqual(result["reason"], "REGION_MISMATCH")
