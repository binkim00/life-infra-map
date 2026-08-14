from django.db import transaction

from recommendations.models import PlaceTag, TagEnrichmentRequest


SUBJECTIVE_TAG_ALIASES = {
    '조용함': ('조용', '한적', '차분', '시끄럽지', '북적이지'),
    '작업하기좋음': ('작업하기 좋', '공부하기 좋', '오래 작업'),
    '노트북작업': ('노트북', '카공', '랩탑'),
    '콘센트있음': ('콘센트', '전원 사용', '충전 가능'),
    '무료와이파이': ('무료 와이파이', '와이파이', 'wifi'),
    '분위기좋음': ('분위기', '감성', '무드', '예쁜', '아늑'),
    '혼밥좋음': ('혼밥', '혼자먹', '혼자 먹', '1인식사', '1인 식사'),
    '데이트좋음': ('데이트', '둘이가기', '둘이 가기'),
    '대화하기좋음': ('대화하기', '얘기하기', '이야기하기'),
    '전망좋음': ('전망', '뷰맛집', '뷰 맛집', '오션뷰', '시티뷰', '야경'),
    '웨이팅적음': ('웨이팅적', '대기적', '안기다', '바로입장'),
}


def normalize_subjective_tags(values, query=''):
    texts = [str(value or '').strip().lower() for value in values or []]
    texts.append(str(query or '').strip().lower())
    matches = []
    for tag, aliases in SUBJECTIVE_TAG_ALIASES.items():
        if any(alias in text for text in texts for alias in aliases):
            matches.append(tag)
    return matches


def enqueue_tag_enrichment(events):
    searches = {
        event.search_id: event
        for event in events
        if event.event_type == 'search' and event.search_id
    }
    queued = 0
    with transaction.atomic():
        for event in events:
            if event.event_type not in {'impression', 'click', 'save'} or not event.place_id:
                continue
            search = searches.get(event.search_id)
            query = event.query or (search.query if search else '')
            requested = event.requested_tags or (search.requested_tags if search else [])
            tags = normalize_subjective_tags(requested, query=query)
            confirmed = set(PlaceTag.objects.filter(
                place_id=event.place_id,
                tag__name__in=tags,
                status='confirmed',
                is_verified=True,
            ).values_list('tag__name', flat=True))
            for tag_name in set(tags) - confirmed:
                request, created = TagEnrichmentRequest.objects.get_or_create(
                    place_id=event.place_id,
                    tag_name=tag_name,
                    defaults={
                        'source_query': query,
                        'context': {'search_id': event.search_id, 'event_type': event.event_type},
                    },
                )
                if not created:
                    request.demand_count += 1
                    request.priority = min(100000, request.priority + 1)
                    request.status = 'queued'
                    request.next_attempt_at = None
                    request.source_query = query or request.source_query
                    request.error_message = ''
                    request.save(update_fields=[
                        'demand_count', 'priority', 'status', 'next_attempt_at', 'source_query',
                        'error_message', 'last_requested_at', 'updated_at',
                    ])
                queued += 1
    return queued
