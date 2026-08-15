from django.db import migrations, models


WEB_EVIDENCE_SOURCES = {
    "naver_blog_search",
    "web_search",
    "ai_suggested",
    "blog_search",
    "naver_search",
}


def relabel_web_aggregates(apps, schema_editor):
    PlaceTag = apps.get_model("recommendations", "PlaceTag")
    PlaceTagEvidence = apps.get_model("recommendations", "PlaceTagEvidence")
    pairs = set(
        PlaceTagEvidence.objects.filter(source__in=WEB_EVIDENCE_SOURCES).values_list(
            "place_id", "tag_id"
        )
    )
    for place_id, tag_id in pairs:
        PlaceTag.objects.filter(
            place_id=place_id,
            tag_id=tag_id,
            source="ai_suggested",
        ).update(source="web_evidence")


def restore_legacy_aggregate_source(apps, schema_editor):
    PlaceTag = apps.get_model("recommendations", "PlaceTag")
    PlaceTag.objects.filter(source="web_evidence").update(source="ai_suggested")


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0017_relabel_naver_blog_evidence"),
    ]

    operations = [
        migrations.AlterField(
            model_name="placetag",
            name="source",
            field=models.CharField(
                choices=[
                    ("category_rule", "카테고리 기반 기본 태그"),
                    ("field_rule", "원본 필드 기반 태그"),
                    ("keyword_rule", "키워드 규칙 기반 태그"),
                    ("blog_search", "블로그 검색 기반 후보 태그"),
                    ("external_api", "외부 API 기반 태그"),
                    ("external_data", "외부 데이터 기반 태그"),
                    ("ai_suggested", "AI 추천 후보 태그"),
                    ("web_evidence", "웹 근거 집계 태그"),
                    ("checked", "검수 완료 태그"),
                    ("user_verified", "사용자 검증 태그"),
                    ("interaction_signal", "검색 행동 기반 후보 태그"),
                    ("warning_tags", "확인 필요 태그"),
                ],
                default="external_data",
                max_length=50,
            ),
        ),
        migrations.RunPython(relabel_web_aggregates, restore_legacy_aggregate_source),
    ]
