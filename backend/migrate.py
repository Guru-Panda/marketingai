"""
Lightweight column-level migrations — works with both SQLite and PostgreSQL.
Called at startup AFTER Base.metadata.create_all so tables already exist
and we only add missing columns without dropping any data.
"""
import logging
from sqlalchemy import text
from backend.database import engine

log = logging.getLogger(__name__)

# (table, column, sqlite_definition, pg_definition)
# pg_definition falls back to sqlite_definition if None
_MIGRATIONS = [
    ("business_strategies", "title",            "VARCHAR(255)",              None),
    ("business_strategies", "buyer_phrases",    "JSON DEFAULT '[]'",         "JSONB DEFAULT '[]'"),
    ("business_strategies", "business_type",    "VARCHAR(20) DEFAULT 'mixed'", None),
    ("business_strategies", "intent_threshold", "REAL",                      "DOUBLE PRECISION"),
    ("suggested_channels",  "strategy_id",      "INTEGER REFERENCES business_strategies(id)", None),
    ("channels",            "strategy_id",      "INTEGER REFERENCES business_strategies(id)", None),
    ("leads",               "strategy_id",      "INTEGER REFERENCES business_strategies(id)", None),
]


def _existing_columns(conn, table: str) -> set[str]:
    url = str(engine.url)
    if "postgresql" in url or "postgres" in url:
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
            {"t": table},
        ).fetchall()
        return {row[0] for row in rows}
    else:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {row[1] for row in rows}


def run_migrations() -> None:
    is_pg = "postgresql" in str(engine.url) or "postgres" in str(engine.url)
    with engine.connect() as conn:
        for table, column, sqlite_def, pg_def in _MIGRATIONS:
            existing = _existing_columns(conn, table)
            if column not in existing:
                definition = (pg_def or sqlite_def) if is_pg else sqlite_def
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
                conn.commit()
                log.info("Migration: added column %s.%s", table, column)
