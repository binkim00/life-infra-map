import hashlib

from django.db import migrations


def relabel_naver_blog_evidence(apps, schema_editor):
    PlaceTagEvidence = apps.get_model("recommendations", "PlaceTagEvidence")
    queryset = PlaceTagEvidence.objects.filter(
        source="ai_suggested",
        raw__channel="naver_blog",
    ).only("id", "place_id", "tag_id", "source_reference", "polarity")
    for evidence in queryset.iterator(chunk_size=1000):
        key_value = "{}|{}|naver_blog_search|{}|{}".format(
            evidence.place_id,
            evidence.tag_id,
            evidence.source_reference,
            evidence.polarity,
        )
        evidence.source = "naver_blog_search"
        evidence.evidence_key = hashlib.sha256(key_value.encode("utf-8")).hexdigest()
        evidence.save(update_fields=["source", "evidence_key"])


def restore_legacy_source(apps, schema_editor):
    PlaceTagEvidence = apps.get_model("recommendations", "PlaceTagEvidence")
    queryset = PlaceTagEvidence.objects.filter(
        source="naver_blog_search",
        raw__channel="naver_blog",
    ).only("id", "place_id", "tag_id", "source_reference", "polarity")
    for evidence in queryset.iterator(chunk_size=1000):
        key_value = "{}|{}|ai_suggested|{}|{}".format(
            evidence.place_id,
            evidence.tag_id,
            evidence.source_reference,
            evidence.polarity,
        )
        evidence.source = "ai_suggested"
        evidence.evidence_key = hashlib.sha256(key_value.encode("utf-8")).hexdigest()
        evidence.save(update_fields=["source", "evidence_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0016_providerquotausage_placetagcollectionjob"),
    ]

    operations = [
        migrations.RunPython(relabel_naver_blog_evidence, restore_legacy_source),
    ]
