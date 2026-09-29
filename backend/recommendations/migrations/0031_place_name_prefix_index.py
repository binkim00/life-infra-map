from django.db import migrations


def create_index(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS place_name_prefix_idx "
            "ON recommendations_place (name varchar_pattern_ops)"
        )


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX CONCURRENTLY IF EXISTS place_name_prefix_idx")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("recommendations", "0030_place_compact_search_indexes")]

    operations = [migrations.RunPython(create_index, drop_index)]
