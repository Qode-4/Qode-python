import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(override=True)

MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "001_create_code_embeddings.sql"


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(database_url)


def init_database() -> None:
    migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(migration_sql)
            conn.commit()
    except psycopg.errors.InsufficientPrivilege as exc:
        raise RuntimeError(
            "Database initialization failed due to insufficient privileges. "
            "The database user must be allowed to create the vector/pgcrypto extensions, "
            "the code_embeddings table, and its indexes."
        ) from exc
    except psycopg.errors.FeatureNotSupported as exc:
        raise RuntimeError(
            "Database initialization failed because the pgvector extension is not available "
            "on this PostgreSQL server. Install pgvector on the database server or use a "
            "PostgreSQL service/image that supports the vector extension."
        ) from exc
