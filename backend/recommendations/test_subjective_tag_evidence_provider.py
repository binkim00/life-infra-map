from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from recommendations.services.subjective_tag_evidence_provider import collect_subjective_tag_evidence


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


@override_settings(
    TAG_ENRICHMENT_ENABLED=True,
    TAG_ENRICHMENT_PROVIDER='openai',
    OPENAI_API_KEY='test-key',
)
class SubjectiveTagEvidenceProviderTests(SimpleTestCase):
    place = SimpleNamespace(
        name='서면 테스트 카페',
        address='부산광역시 부산진구',
        category='cafe',
    )

    def test_requires_citation_and_identity_match(self):
        payload = {
            'output': [{'type': 'message', 'content': [{
                'type': 'output_text',
                'text': '{"polarity":"positive","evidence_summary":"평일에는 조용하다고 설명한다.","identity_match":true}',
                'annotations': [{
                    'type': 'url_citation',
                    'url': 'https://example.com/cafe',
                    'title': '카페 공식 소개',
                }],
            }]}],
        }
        result = collect_subjective_tag_evidence(
            self.place,
            '조용함',
            request_post=lambda *args, **kwargs: FakeResponse(payload),
        )

        self.assertEqual(result['polarity'], 'positive')
        self.assertEqual(result['source_url'], 'https://example.com/cafe')

    def test_rejects_model_claim_without_citation(self):
        payload = {'output_text': '{"polarity":"positive","evidence_summary":"조용하다.","identity_match":true}'}
        result = collect_subjective_tag_evidence(
            self.place,
            '조용함',
            request_post=lambda *args, **kwargs: FakeResponse(payload),
        )

        self.assertEqual(result['polarity'], 'unknown')
        self.assertEqual(result['error'], 'insufficient_evidence')
