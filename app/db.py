"""SQLite via SQLAlchemy 2 (sync). See PLAN.md §5."""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import S


class Base(DeclarativeBase):
    pass


engine = create_engine(S.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create data/ and all tables. Safe to call more than once."""
    if S.DATABASE_URL.startswith("sqlite:///") and ":memory:" not in S.DATABASE_URL:
        path = S.DATABASE_URL.removeprefix("sqlite:///")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    from app import models  # noqa: F401  (registers the tables on Base)

    Base.metadata.create_all(engine)


@contextmanager
def session():
    """Yield a Session; commit on success, roll back on error."""
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
