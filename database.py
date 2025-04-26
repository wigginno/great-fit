import os
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


def _build_database_url() -> str:
    """Determine the SQLAlchemy DB URL using env vars with sensible fallbacks."""
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    host = os.getenv("DB_HOST")
    if host:
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "postgres")
        return f"postgresql://{user}:{password}@{host}:{port}/{name}"

    # Default to local SQLite file for simple local development
    return "sqlite:///./great_fit.db"


SQLALCHEMY_DATABASE_URL = _build_database_url()

# Configure SQLAlchemy engine – extra connect args only relevant for SQLite
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={
            "check_same_thread": False,
            "timeout": 15,
        },
        pool_pre_ping=True,
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)

# Apply WAL / timeout pragmas only when using SQLite
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.execute("PRAGMA synchronous=NORMAL;")
        finally:
            cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def create_db_and_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
