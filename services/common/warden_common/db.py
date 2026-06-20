"""Engine/session helpers. Works against Postgres (prod) and SQLite (tests)."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import db_settings
from .models import Base

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def init_engine(url: str | None = None, *, create_all: bool = False) -> Engine:
    global _engine, _Session
    url = url or db_settings().database_url
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    _engine = create_engine(url, connect_args=connect_args, future=True)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    if create_all:
        Base.metadata.create_all(_engine)
        if url.startswith("postgresql"):
            apply_postgres_hardening(_engine)
    return _engine


# A defense-in-depth layer: even with direct DB access, no one can rewrite
# history. The ledger API never issues UPDATE/DELETE on audit_log; this trigger
# guarantees the database rejects them too. "Immutable" enforced by the engine,
# not by convention.
_APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION warden_block_audit_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % rejected', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS warden_audit_append_only ON audit_log;
CREATE TRIGGER warden_audit_append_only
BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_log
FOR EACH STATEMENT EXECUTE FUNCTION warden_block_audit_mutation();
"""


def apply_postgres_hardening(engine: Engine) -> None:
    """Install the append-only trigger on Postgres. No-op elsewhere."""
    with engine.begin() as conn:
        conn.execute(text(_APPEND_ONLY_SQL))


def _ensure() -> sessionmaker[Session]:
    global _Session
    if _Session is None:
        init_engine()
    assert _Session is not None
    return _Session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope around a series of operations."""
    factory = _ensure()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
