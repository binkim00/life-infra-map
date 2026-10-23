"""Read-time validity for materialized human/user confirmation tags."""

from django.db.models import BooleanField, Case, Exists, OuterRef, Q, When
from django.utils import timezone

from recommendations.models import PlaceTag, PlaceTagEvidence
from .tag_source_policy import WEB_EVIDENCE_SOURCES


CONFIRMATION_SOURCES = frozenset({"checked", "user_verified"})
SUPPORT_ATTRIBUTE = "_has_current_confirmation_evidence"


def confirmation_aware_place_tags(*, now=None):
    """Keep manual decisions intact; annotate whether their evidence is current.

    Unreviewed human/official observations retain the existing acceptance
    policy. Web observations require approval, as in the common hard gate.
    """
    now = now or timezone.now()
    support = PlaceTagEvidence.objects.filter(
        place_id=OuterRef("place_id"), tag_id=OuterRef("tag_id"),
        polarity="positive",
    ).filter(
        Q(review__status="approved")
        | (Q(review__isnull=True) & ~Q(source__in=WEB_EVIDENCE_SOURCES))
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    return PlaceTag.objects.select_related("tag").annotate(**{
        SUPPORT_ATTRIBUTE: Case(
            When(source__in=CONFIRMATION_SOURCES, then=Exists(support)),
            default=True, output_field=BooleanField(),
        ),
    })


def effective_place_tags(place):
    """Exclude unsupported confirmations from every current tag list.

    An old confirmation must not become a suggested tag that can satisfy a
    search condition. Do not invent a historical observation for missing
    evidence, and never update the stored confirmation or review.
    """
    rows = list(place.place_tags.all())
    missing = [
        row.pk for row in rows
        if row.source in CONFIRMATION_SOURCES
        and not hasattr(row, SUPPORT_ATTRIBUTE)
    ]
    support = dict(
        confirmation_aware_place_tags().filter(pk__in=missing).values_list(
            "pk", SUPPORT_ATTRIBUTE,
        )
    ) if missing else {}
    return [
        row for row in rows
        if row.source not in CONFIRMATION_SOURCES
        or getattr(row, SUPPORT_ATTRIBUTE, support.get(row.pk, False))
    ]
