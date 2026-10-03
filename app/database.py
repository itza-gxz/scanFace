from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .utils import DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if _is_sqlite else {})

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
