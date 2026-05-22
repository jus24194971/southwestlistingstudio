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
    """Create all tables. Idempotent. Called once at app startup."""
    engine = init_engine()
    Base.metadata.create_all(engine)


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
