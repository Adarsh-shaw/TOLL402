from collections.abc import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import get_settings


class Base(DeclarativeBase):
    pass


def _build_engine():
    settings = get_settings()
    db_url = settings.database_url
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    eng = create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )
    if db_url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    return eng


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models so SQLAlchemy registers metadata
    from backend.app.models import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
