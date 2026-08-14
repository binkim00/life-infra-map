import requests
from django.conf import settings

from recommendations.services.ai_web_search_provider import (
    _extract_response_texts_and_sources,
    _get_responses_api_config,
    _parse_ai_provider_response,
    _safe_text,
)


def collect_subjective_tag_evidence(place, tag_name, *, request_post=None):
    provider = getattr(settings, 'TAG_ENRICHMENT_PROVIDER', 'openai')
    if provider == 'naver_search':
        if not getattr(settings, 'TAG_ENRICHMENT_ENABLED', False):
            return {'executed': False, 'error': 'not_configured'}
        from recommendations.services.naver_tag_evidence_provider import collect_naver_tag_evidence
        return collect_naver_tag_evidence(place, tag_name)
    if provider not in {'openai', 'gms'}:
        return {'executed': False, 'error': 'unsupported_provider'}
    api_key, api_url = _get_responses_api_config(provider)
    if not api_key or not api_url or not getattr(settings, 'TAG_ENRICHMENT_ENABLED', False):
        return {'executed': False, 'error': 'not_configured'}

    instructions = (
        'Use web_search to verify one subjective attribute of one exact Korean place. '
        'Use only sources that clearly identify the same place by name plus address, phone, or branch. '
        'Return JSON only with polarity positive, negative, or unknown; evidence_summary; identity_match. '
        'Do not infer an attribute from category, place name, ranking, or search snippet alone. '
        'If the evidence is ambiguous or lacks a source, return unknown.'
    )
    input_text = (
        'place_name: {}\naddress: {}\ncategory: {}\nattribute: {}\n'
        'Return {{\'polarity\':\'positive|negative|unknown\',\'evidence_summary\':\'short Korean evidence\','
        '\'identity_match\':true|false}}.'
    ).format(place.name, place.address, place.category, tag_name)
    payload = {
        'model': getattr(settings, 'AI_WEB_SEARCH_MODEL', 'gpt-5-nano'),
        'instructions': instructions,
        'input': input_text,
        'tools': [{'type': 'web_search'}],
        'tool_choice': 'auto',
        'max_output_tokens': 600,
    }
    headers = {'Authorization': 'Bearer {}'.format(api_key), 'Content-Type': 'application/json'}
    post = request_post or requests.post
    try:
        response = post(
            api_url, headers=headers, json=payload,
            timeout=getattr(settings, 'AI_REQUEST_TIMEOUT', 20),
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return {'executed': True, 'error': 'request_failed'}

    texts, sources = _extract_response_texts_and_sources(data)
    parsed = _parse_ai_provider_response(data)
    polarity = _safe_text(parsed.get('polarity'), 20).lower()
    summary = _safe_text(parsed.get('evidence_summary'), 500)
    identity_match = parsed.get('identity_match') is True
    source = sources[0] if sources else {}
    source_url = _safe_text(source.get('url'), 500)
    if polarity not in {'positive', 'negative'} or not identity_match or not summary or not source_url.startswith(('http://', 'https://')):
        return {'executed': True, 'polarity': 'unknown', 'error': 'insufficient_evidence'}
    return {
        'executed': True,
        'polarity': polarity,
        'evidence_summary': summary,
        'source_url': source_url,
        'source_title': _safe_text(source.get('title'), 120),
        'raw': {'response_text': _safe_text('\n'.join(texts), 2000)},
    }
