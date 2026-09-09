from contextlib import asynccontextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import close_all_sessions, sessionmaker

from backend.services import db_service
from backend.services.db_service import Base


def configure_test_db(monkeypatch, tmp_path, filename: str):
    db_path = tmp_path / filename
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(db_service, "DATABASE_URL", database_url)
    monkeypatch.setattr(db_service, "engine", engine)
    monkeypatch.setattr(db_service, "SessionLocal", session_local)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine


def teardown_test_db(engine) -> None:
    Base.metadata.drop_all(bind=engine)
    close_all_sessions()
    engine.dispose()


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


def disable_app_lifespan(monkeypatch, app) -> None:
    monkeypatch.setattr(app.router, "lifespan_context", _noop_lifespan)
