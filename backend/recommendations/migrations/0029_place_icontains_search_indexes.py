from django.db import migrations


INDEXES = (
    ("place_name_icontains_trgm_idx", "name"),
    ("place_address_icontains_trgm_idx", "address"),
)


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for index_name, field in INDEXES:
        schema_editor.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name} "
            f"ON recommendations_place USING GIN "
            f"(upper({field}::text) gin_trgm_ops)"
        )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for index_name, _ in INDEXES:
        schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("recommendations", "0028_alter_evidencereview_status")]

    operations = [migrations.RunPython(create_indexes, drop_indexes)]
