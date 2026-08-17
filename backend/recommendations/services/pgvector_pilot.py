import time

import psycopg


def vector_literal(values):
    return "[" + ",".join(f"{float(value):.9g}" for value in values) + "]"


def connect_pilot(dsn):
    connection = psycopg.connect(dsn)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        database = cursor.fetchone()[0]
    if "pilot" not in database.lower():
        connection.close()
        raise RuntimeError("pgvector_dsn_must_target_a_pilot_database")
    return connection


def ensure_pilot_schema(connection, *, dimensions):
    if int(dimensions) != 512:
        raise ValueError("pilot_schema_requires_512_dimensions")
    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS place_feature_embedding (
                document_id bigint PRIMARY KEY,
                place_id bigint NOT NULL,
                source_hash varchar(64) NOT NULL,
                provider varchar(50) NOT NULL,
                model varchar(100) NOT NULL,
                dimensions smallint NOT NULL,
                strategy varchar(30) NOT NULL,
                embedding vector(512) NOT NULL,
                embedded_at timestamptz NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS semantic_pilot_embedding_hnsw
            ON place_feature_embedding USING hnsw (embedding vector_cosine_ops)
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS semantic_pilot_place_idx ON place_feature_embedding(place_id)")
    connection.commit()


def upsert_documents(connection, documents):
    rows = [(
        document.id, document.place_id, document.embedding_source_hash,
        document.embedding_provider, document.embedding_model, document.embedding_dimensions,
        document.embedding_strategy, vector_literal(document.embedding), document.indexed_at,
    ) for document in documents]
    started = time.perf_counter()
    with connection.cursor() as cursor:
        cursor.executemany("""
            INSERT INTO place_feature_embedding (
                document_id, place_id, source_hash, provider, model, dimensions,
                strategy, embedding, embedded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s)
            ON CONFLICT (document_id) DO UPDATE SET
                place_id=EXCLUDED.place_id, source_hash=EXCLUDED.source_hash,
                provider=EXCLUDED.provider, model=EXCLUDED.model,
                dimensions=EXCLUDED.dimensions, strategy=EXCLUDED.strategy,
                embedding=EXCLUDED.embedding, embedded_at=EXCLUDED.embedded_at
            WHERE place_feature_embedding.source_hash <> EXCLUDED.source_hash
               OR place_feature_embedding.model <> EXCLUDED.model
               OR place_feature_embedding.dimensions <> EXCLUDED.dimensions
               OR place_feature_embedding.strategy <> EXCLUDED.strategy
        """, rows)
    connection.commit()
    return round((time.perf_counter() - started) * 1000, 2)


def sql_vector_search(connection, query_vector, *, top_k=10):
    started = time.perf_counter()
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT document_id, place_id, 1 - (embedding <=> %s::vector) AS similarity
            FROM place_feature_embedding
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (vector_literal(query_vector), vector_literal(query_vector), max(1, min(int(top_k), 50))))
        rows = cursor.fetchall()
    return rows, round((time.perf_counter() - started) * 1000, 2)
