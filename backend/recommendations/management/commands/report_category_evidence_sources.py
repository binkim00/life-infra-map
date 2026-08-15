import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from recommendations.models import Place, PlaceTagEvidence
from recommendations.services.place_tag_collection import COLLECTION_PROFILES


SOURCE_POLICY = {
    "cafe": ["naver_blog_search", "Place.raw/Kakao metadata"],
    "restaurant": ["naver_blog_search", "Place.raw/Kakao metadata"],
    "tourism": ["tour_api/Place.raw", "external_api detail", "naver_blog_search supplement"],
    "city_park": ["citypark_standard/Place.raw", "field_rule", "naver_blog_search supplement"],
    "library": ["library standard/Place.raw", "official homepage", "naver_blog_search supplement"],
    "beach": ["beach_api/Place.raw", "official/local government", "naver_blog_search supplement"],
    "parking": ["public_parking_standard/Place.raw", "field_rule", "naver_blog_search supplement"],
    "toilet": ["public_toilet_standard/Place.raw", "field_rule", "naver_blog_search last"],
    "shelter": ["heat_shelter_api/Place.raw", "field_rule", "naver_blog_search last"],
}


class Command(BaseCommand):
    help = "Report current place/evidence source coverage and preferred source order by category."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="tmp/category_evidence_sources.json")

    def handle(self, *args, **options):
        report = {}
        for category in COLLECTION_PROFILES:
            places = Place.objects.filter(category=category)
            report[category] = {
                "places": places.count(),
                "place_sources": dict(Counter(places.values_list("source", flat=True))),
                "evidence_sources": dict(Counter(
                    PlaceTagEvidence.objects.filter(place__category=category).values_list("source", flat=True)
                )),
                "preferred_order": SOURCE_POLICY.get(category, []),
            }
        path = Path(options["output"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps({"output": str(path), "categories": len(report)}, ensure_ascii=False))
