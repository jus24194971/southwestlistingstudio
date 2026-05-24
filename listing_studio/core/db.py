"""SQLAlchemy engine, session factory, and one-time initialization.

Uses SQLite with WAL mode for better concurrent read performance (the UI may
read while a background post is being logged).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from listing_studio.config import settings
from listing_studio.core.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _configure_sqlite(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
    """SQLite-specific PRAGMA tuning, applied on every new connection.

    - WAL mode: lets the UI read templates while a background task writes a post.
    - Foreign keys: SQLite disables these by default; we need them enforced.
    - Synchronous NORMAL: a good speed/durability tradeoff for desktop use.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.close()


def init_engine() -> Engine:
    """Create the engine if it doesn't exist yet, and return it.

    Idempotent - safe to call multiple times.
    """
    global _engine, _SessionLocal

    if _engine is not None:
        return _engine

    settings.ensure_dirs()

    _engine = create_engine(
        settings.db_url,
        # check_same_thread False is required because pywebview and FastAPI run on
        # different threads, and the SQLAlchemy session is shared across them.
        connect_args={"check_same_thread": False},
        # Echo SQL in development? Not by default; tail the logs instead.
        echo=False,
    )

    event.listen(_engine, "connect", _configure_sqlite)

    _SessionLocal = sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,  # Detached objects stay usable after session close
    )

    return _engine


def init_db() -> None:
    """Create all tables, run lightweight migrations, seed reference data.

    Idempotent. Order matters: schema must exist before migrations alter it,
    and migrations must finish before we try to insert seed rows that
    depend on new columns.
    """
    engine = init_engine()
    Base.metadata.create_all(engine)
    _run_migrations(engine)
    _seed_reference_data()


def _seed_reference_data() -> None:
    """Insert shipped reference rows (currently just category mappings).

    Wrapped in its own try/except so a seed failure can't block the app
    from starting - the worst case is the suggestion engine has no shipped
    mappings until the next run.
    """
    try:
        from listing_studio.core import category_suggest
        with session_scope() as session:
            category_suggest.seed_shipped_mappings_if_missing(session)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("Reference data seed failed: %s", exc)


def _run_migrations(engine: Engine) -> None:
    """Apply additive schema changes for existing databases.

    SQLAlchemy's create_all() doesn't add new columns to existing tables - it
    only creates tables that don't exist yet. So when we add a column to a
    model, we have to ALTER TABLE manually.

    This is a deliberately simple approach. For each known column-addition,
    we check if it already exists and ALTER if not. SQLite supports
    ALTER TABLE ADD COLUMN since forever; it's fast and safe.

    If we ever do anything more complex (renames, type changes), we'd switch
    to Alembic. For now this is fine.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)

    # Map of (table_name -> {column_name: SQL type fragment}). Each ALTER runs
    # only if the column is missing. Skipping the table entirely is fine if
    # the table doesn't exist yet - create_all() handles that case.
    needed_columns: dict[str, dict[str, str]] = {
        "templates": {
            "model": "TEXT",
            "year": "TEXT",
            "finish": "TEXT",
            "reverb_category": "TEXT",
            "reverb_subcategories": "TEXT",
            "category_id": "INTEGER REFERENCES categories(id)",
            "reverb_shipping_type": "TEXT",
            "reverb_shipping_flat_cents": "INTEGER NOT NULL DEFAULT 0",
            "ebay_shipping_type": "TEXT",
            "ebay_shipping_override_cents": "INTEGER NOT NULL DEFAULT 0",
        },
        "categories": {
            "ebay_category_id": "INTEGER",
            "ebay_category_name": "TEXT",
            "ebay_category_path": "TEXT",
            # SQLite has no real BOOLEAN; store as INTEGER. Default 1 (true)
            # because the existing column-less data assumed leaf-only.
            "ebay_leaf": "INTEGER NOT NULL DEFAULT 1",
            "squarespace_store_page_id": "TEXT",
            "squarespace_store_page_name": "TEXT",
        },
    }

    with engine.begin() as conn:
        for table_name, cols in needed_columns.items():
            try:
                existing = {c["name"] for c in inspector.get_columns(table_name)}
            except Exception:
                # Table doesn't exist yet (create_all just made it new with
                # the right schema); skip the ALTERs.
                continue
            for col_name, col_type in cols.items():
                if col_name not in existing:
                    # SQLite ALTER TABLE syntax. col_name/col_type come from
                    # the hardcoded dict above, not user input.
                    conn.execute(text(
                        f'ALTER TABLE {table_name} ADD COLUMN "{col_name}" {col_type}'
                    ))


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional session as a context manager.

    Commits on success, rolls back on exception, always closes.

        with session_scope() as session:
            template = session.query(Template).get(1)
            ...
    """
    if _SessionLocal is None:
        init_engine()
        assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Session:
    """Get a raw session. Caller is responsible for commit/rollback/close.

    Prefer ``session_scope()`` when you can; this exists for FastAPI dependency
    injection where the framework manages the lifecycle.
    """
    if _SessionLocal is None:
        init_engine()
        assert _SessionLocal is not None
    return _SessionLocal()
