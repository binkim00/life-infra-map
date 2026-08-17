import hashlib
import re

from django.db.models import Q
from django.utils import timezone

from recommendations.models import PlaceTagEvidence


TRUSTED_REVIEW_SOURCES = {"checked", "user_verified"}
DOCUMENT_STRATEGIES = {"tags", "contextual", "full"}


def active_feature_names(place, *, now=None):
    now = now or timezone.now()
    active_pairs = {
        (row["tag_id"], row["polarity"])
        for row in PlaceTagEvidence.objects.filter(place=place).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).values("tag_id", "polarity")
    }
    names = []
    for place_tag in place.place_tags.select_related("tag").all():
        if place_tag.status in {"rejected", "needs_verification"}:
            continue
        positive = (place_tag.tag_id, "positive") in active_pairs
        negative = (place_tag.tag_id, "negative") in active_pairs
        trusted_review = place_tag.source in TRUSTED_REVIEW_SOURCES and place_tag.is_verified
        if place_tag.status == "confirmed" and (positive and not negative or trusted_review):
            names.append(place_tag.tag.name)
        elif place_tag.status == "candidate" and place_tag.confidence >= 50 and positive and not negative:
            names.append(place_tag.tag.name)
    return sorted(set(names))


def build_place_feature_document(place, *, now=None):
    features = active_feature_names(place, now=now)
    parts = [place.name, place.category]
    if place.address:
        parts.append(place.address)
    parts.extend(features)
    document = " / ".join(part for part in parts if part)
    fingerprint = hashlib.sha256(document.encode("utf-8")).hexdigest()
    return {"document": document, "features": features, "fingerprint": fingerprint}


def embedding_document(document, *, strategy="contextual"):
    """Render only stored facts; never synthesize recommendation prose."""
    if strategy not in DOCUMENT_STRATEGIES:
        raise ValueError(f"unsupported_document_strategy:{strategy}")
    place = document.place
    features = sorted(set(document.features or []))
    if strategy == "tags":
        return " / ".join(features)
    if strategy == "full":
        return document.document
    region_match = re.match(
        r"^(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)",
        place.address or "",
    )
    region = region_match.group(1) if region_match else ""
    return " / ".join(
        part for part in [place.name, place.category, region, *features] if part
    )


def embedding_source_hash(document, *, strategy):
    text = embedding_document(document, strategy=strategy)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
