import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15} if url.startswith("sqlite") else {}, pool_pre_ping=True)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
    return engine


def configure_database(url: str | None = None):
    engine = make_engine(url or os.getenv("DATABASE_URL", "sqlite:///./annotations.db"))
    return engine, sessionmaker(engine, expire_on_commit=False)
