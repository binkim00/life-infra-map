import re

from django.db import transaction
from django.utils import timezone

from recommendations.models import Tag, UserPreference, UserSearchLog


PREFERENCE_SCORE_CAP = 100.0
PERSONALIZATION_BOOST_CAP = 5.0
MAX_LABEL_LENGTH = 100
MAX_USER_SELECTED_LABEL_LENGTH = 50
MAX_TARGET_QUERY_LENGTH = 60
SEARCH_LOG_SOURCE = "search_log"
USER_SELECTED_SOURCE = "user_selected"
USER_SELECTED_SCORE = 10.0
USER_SELECTED_BOOST_MULTIPLIER = 1.5
ALLOWED_USER_SELECTED_TYPES = {"tag", "condition", "menu", "place_type", "category"}
LABEL_VALUE_KEYS = [
    "label",
    "name",
    "display_name",
    "displayName",
    "value",
    "text",
]
INVALID_LABEL_VALUES = {"[object object]"}
HTML_TAG_RE = re.compile(r"<[^>]*>")

PREFERENCE_WEIGHTS = {
    "tag": 2.0,
    "condition": 1.5,
    "menu": 1.5,
    "place_type": 1.2,
    "category": 1.0,
    "scenario": 0.8,
    "keyword": 0.5,
}

PREFERENCE_TYPE_LABELS = {
    "tag": "조건",
    "condition": "조건",
    "menu": "메뉴",
    "place_type": "장소 유형",
    "category": "카테고리",
    "scenario": "상황",
    "keyword": "키워드",
}


def normalize_preference_label(value):
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, bool) or value is None:
        return ""

    if isinstance(value, (int, float)):
        return str(value).strip()

    if isinstance(value, dict):
        for key in LABEL_VALUE_KEYS:
            label = normalize_preference_label(value.get(key))
            if label:
                return label
        return ""

    return ""


def normalize_preference_key(value):
    return normalize_preference_label(value).lower()


def is_valid_preference_label(label, max_length=MAX_LABEL_LENGTH):
    normalized_label = normalize_preference_label(label)
    return (
        bool(normalized_label)
        and len(normalized_label) <= max_length
        and normalized_label.lower() not in INVALID_LABEL_VALUES
    )


def unique_valid_labels(values, max_length=MAX_LABEL_LENGTH):
    if not isinstance(values, list):
        return []

    seen = set()
    labels = []

    for value in values:
        label = normalize_preference_label(value)
        key = normalize_preference_key(label)

        if not is_valid_preference_label(label, max_length=max_length):
            continue
        if key in seen:
            continue

        seen.add(key)
        labels.append(label)

    return labels


def clean_user_selected_label(value):
    label = normalize_preference_label(value)
    if not label or HTML_TAG_RE.search(label):
        return ""

    return re.sub(r"\s+", " ", label).strip()


@transaction.atomic
def create_or_update_user_selected_preference(user, preference_type, label):
    preference_type = normalize_preference_label(preference_type) or "tag"
    if preference_type not in ALLOWED_USER_SELECTED_TYPES:
        raise ValueError("지원하지 않는 선호 유형입니다.")

    cleaned_label = clean_user_selected_label(label)
    if not is_valid_preference_label(cleaned_label, max_length=MAX_USER_SELECTED_LABEL_LENGTH):
        raise ValueError("선호 키워드를 다시 확인해 주세요.")

    key = normalize_preference_key(cleaned_label)
    now = timezone.now()
    preference, created = UserPreference.objects.select_for_update().get_or_create(
        user=user,
        preference_type=preference_type,
        key=key,
        defaults={
            "label": cleaned_label,
            "score": USER_SELECTED_SCORE,
            "search_count": 0,
            "source": USER_SELECTED_SOURCE,
            "last_seen_at": now,
        },
    )

    if not created:
        preference.label = cleaned_label
        preference.score = max(float(preference.score or 0), USER_SELECTED_SCORE)
        preference.source = USER_SELECTED_SOURCE
        preference.last_seen_at = now
        preference.save(
            update_fields=[
                "label",
                "score",
                "source",
                "last_seen_at",
                "updated_at",
            ],
        )

    return preference, created


@transaction.atomic
def create_or_update_user_selected_tag_preference(user, tag):
    if not isinstance(tag, Tag):
        raise ValueError("태그를 다시 확인해 주세요.")

    label = normalize_preference_label(tag.name)
    if not is_valid_preference_label(label, max_length=MAX_USER_SELECTED_LABEL_LENGTH):
        raise ValueError("태그를 다시 확인해 주세요.")

    key = normalize_preference_key(label)
    now = timezone.now()
    preference, created = UserPreference.objects.select_for_update().get_or_create(
        user=user,
        preference_type="tag",
        key=key,
        defaults={
            "label": label,
            "score": USER_SELECTED_SCORE,
            "search_count": 0,
            "source": USER_SELECTED_SOURCE,
            "last_seen_at": now,
        },
    )

    if not created:
        preference.label = label
        preference.score = max(float(preference.score or 0), USER_SELECTED_SCORE)
        preference.source = USER_SELECTED_SOURCE
        preference.last_seen_at = now
        preference.save(
            update_fields=[
                "label",
                "score",
                "source",
                "last_seen_at",
                "updated_at",
            ],
        )

    return preference, created


def iter_preference_entries_from_search_log(search_log):
    field_map = [
        ("tag", search_log.preferred_tags),
        ("condition", search_log.requested_conditions),
        ("menu", search_log.menu_keywords),
        ("place_type", search_log.place_type_keywords),
    ]

    for preference_type, values in field_map:
        for label in unique_valid_labels(values):
            yield preference_type, normalize_preference_key(label), label, PREFERENCE_WEIGHTS[preference_type]

    scalar_fields = [
        ("category", search_log.category_hint, MAX_LABEL_LENGTH),
        ("scenario", search_log.scenario, MAX_LABEL_LENGTH),
        ("keyword", search_log.target_query, MAX_TARGET_QUERY_LENGTH),
    ]

    for preference_type, value, max_length in scalar_fields:
        label = normalize_preference_label(value)
        if not is_valid_preference_label(label, max_length=max_length):
            continue

        yield preference_type, normalize_preference_key(label), label, PREFERENCE_WEIGHTS[preference_type]


@transaction.atomic
def update_user_preferences_from_search_log(search_log):
    updated_count = 0
    seen_entries = set()

    for preference_type, key, label, weight in iter_preference_entries_from_search_log(search_log):
        entry_key = (preference_type, key)
        if entry_key in seen_entries:
            continue

        seen_entries.add(entry_key)
        preference, created = UserPreference.objects.select_for_update().get_or_create(
            user=search_log.user,
            preference_type=preference_type,
            key=key,
            defaults={
                "label": label,
                "score": 0,
                "search_count": 0,
                "source": SEARCH_LOG_SOURCE,
                "last_seen_at": search_log.created_at,
            },
        )
        preference.label = preference.label or label
        preference.score = min(PREFERENCE_SCORE_CAP, float(preference.score or 0) + weight)
        preference.search_count = int(preference.search_count or 0) + 1
        if preference.source != USER_SELECTED_SOURCE:
            preference.source = SEARCH_LOG_SOURCE
            preference.last_seen_at = search_log.created_at
        elif not preference.last_seen_at or search_log.created_at > preference.last_seen_at:
            preference.last_seen_at = search_log.created_at
        preference.save(
            update_fields=[
                "label",
                "score",
                "search_count",
                "source",
                "last_seen_at",
                "updated_at",
            ],
        )
        updated_count += 1 if created or weight else 0

    return updated_count


@transaction.atomic
def rebuild_user_preferences(user):
    UserPreference.objects.filter(user=user, key__iexact="[object object]").delete()
    UserPreference.objects.filter(user=user, label__iexact="[object object]").delete()
    UserPreference.objects.filter(user=user, source=SEARCH_LOG_SOURCE).delete()

    for search_log in UserSearchLog.objects.filter(user=user).order_by("created_at", "id"):
        update_user_preferences_from_search_log(search_log)

    return UserPreference.objects.filter(user=user).count()


def get_user_preference_lookup(user):
    if not user or not getattr(user, "is_authenticated", False):
        return {}

    preferences = UserPreference.objects.filter(user=user, score__gt=0).order_by("-score")[:100]
    lookup = {}

    for preference in preferences:
        lookup.setdefault(preference.preference_type, {})[preference.key] = preference

    return lookup


def _source_multiplier(preference):
    return USER_SELECTED_BOOST_MULTIPLIER if preference.source == USER_SELECTED_SOURCE else 1.0


def _preference_contribution(preference, multiplier, max_contribution):
    contribution = min(float(preference.score or 0) * multiplier, max_contribution)
    return contribution * _source_multiplier(preference)


def _personalization_reason(preference):
    if preference.source == USER_SELECTED_SOURCE:
        if preference.preference_type == "tag":
            return f"직접 선택한 선호 태그와 일치: {preference.label}"
        return f"직접 선택한 선호와 일치: {preference.label}"

    return f"최근 검색 선호와 일부 일치: {preference.label}"


def calculate_personalization_boost(
    place,
    tag_data,
    scenario,
    preference_lookup,
):
    if not preference_lookup:
        return 0.0, []

    boost = 0.0
    reasons = []
    matched_keys = set()
    tag_names = (
        tag_data.get("verified_tags", [])
        + tag_data.get("suggested_tags", [])
        + tag_data.get("warning_tags", [])
    )

    for preference_type in ["tag", "condition"]:
        type_preferences = preference_lookup.get(preference_type, {})
        for tag_name in tag_names:
            key = normalize_preference_key(tag_name)
            preference = type_preferences.get(key)
            if not preference or (preference_type, key) in matched_keys:
                continue

            matched_keys.add((preference_type, key))
            boost += _preference_contribution(preference, 0.18, 2.0)
            reasons.append(_personalization_reason(preference))

    category_preference = preference_lookup.get("category", {}).get(
        normalize_preference_key(place.category)
    )
    if category_preference:
        boost += _preference_contribution(category_preference, 0.08, 1.0)
        reasons.append(_personalization_reason(category_preference))

    scenario_preference = preference_lookup.get("scenario", {}).get(
        normalize_preference_key(scenario)
    )
    if scenario_preference:
        boost += _preference_contribution(scenario_preference, 0.05, 0.8)
        reasons.append(_personalization_reason(scenario_preference))

    searchable_text = normalize_preference_key(
        " ".join([
            place.name,
            place.category,
            place.address,
            place.detail_location,
            place.source_name,
            " ".join(tag_names),
        ])
    )

    for preference_type in ["menu", "place_type", "keyword"]:
        for key, preference in preference_lookup.get(preference_type, {}).items():
            if not key or key not in searchable_text or (preference_type, key) in matched_keys:
                continue

            matched_keys.add((preference_type, key))
            boost += _preference_contribution(preference, 0.06, 0.8)
            reasons.append(_personalization_reason(preference))

    applied_boost = min(round(boost, 2), PERSONALIZATION_BOOST_CAP)
    return applied_boost, reasons[:3] if applied_boost else []
