from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import SUPABASE_DATABASE_URL
from src.db.models import Base

_engine = None
_SessionLocal = None


def is_database_configured() -> bool:
    return bool(SUPABASE_DATABASE_URL)


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_engine():
    global _engine

    if not SUPABASE_DATABASE_URL:
        raise RuntimeError("SUPABASE_DATABASE_URL nao configurada.")

    if _engine is None:
        _engine = create_engine(
            _normalize_database_url(SUPABASE_DATABASE_URL),
            pool_pre_ping=True,
        )

    return _engine


def get_session():
    global _SessionLocal

    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
        )

    return _SessionLocal()


def init_database() -> None:
    Base.metadata.create_all(bind=get_engine())
