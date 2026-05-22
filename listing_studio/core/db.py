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
    """Create all tables, then run lightweight migrations. Idempotent."""
    engine = init_engine()
    Base.metadata.create_all(engine)
    _run_migrations(engine)


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
    existing_columns = {col["name"] for col in inspector.get_columns("templates")}

    # Map of column name -> SQL fragment for the ALTER
    needed_columns = {
        "model": "TEXT",
        "year": "TEXT",
        "finish": "TEXT",
        "reverb_category": "TEXT",
        "reverb_subcategories": "TEXT",
        "category_id": "INTEGER REFERENCES categories(id)",
    }

    with engine.begin() as conn:
        for col_name, col_type in needed_columns.items():
            if col_name not in existing_columns:
                # SQLite ALTER TABLE syntax. Using parameterless string interpolation
                # is safe here because col_name/col_type come from our hardcoded
                # dict above, not user input.
                conn.execute(text(f'ALTER TABLE templates ADD COLUMN "{col_name}" {col_type}'))


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
