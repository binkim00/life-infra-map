"""
장소 좌표를 PostGIS geography 컬럼으로 만들고 GiST 인덱스를 붙입니다.

지금까지는 bounding box 로 SQL 에서 대략 좁힌 뒤,
파이썬에서 행마다 하버사인을 돌려 반경 밖을 걸러냈습니다.
`ST_DWithin` 은 정확한 반경 조건을 인덱스로 처리하므로 두 단계가 한 번에 끝납니다.

`lat`/`lng` 에서 자동으로 계산되는 생성 컬럼이라 애플리케이션이 따로 채울 필요가 없고,
기존 `lat`/`lng` 컬럼은 외부 API와의 좌표 교환을 위해 함께 유지합니다.
"""

from django.db import migrations


def create_geography(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cursor.execute(
            """
            ALTER TABLE recommendations_place
            ADD COLUMN IF NOT EXISTS geog geography(Point, 4326)
            GENERATED ALWAYS AS (
                ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography
            ) STORED
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS recommendations_place_geog_gist "
            "ON recommendations_place USING gist (geog)"
        )
        cursor.execute("ANALYZE recommendations_place")


def drop_geography(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS recommendations_place_geog_gist")
        cursor.execute("ALTER TABLE recommendations_place DROP COLUMN IF EXISTS geog")


class Migration(migrations.Migration):

    dependencies = [
        ("recommendations", "0008_place_recommendat_lat_4407f8_idx"),
    ]

    operations = [
        migrations.RunPython(create_geography, drop_geography),
    ]
