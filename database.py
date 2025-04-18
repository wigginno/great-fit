from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./great_fit.db"
# SQLALCHEMY_DATABASE_URL = "postgresql://user:password@postgresserver/db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "check_same_thread": False,  # Needed only for SQLite
        "timeout": 15,  # Increase timeout (default is 5 seconds)
    },
    pool_pre_ping=True,  # Check connections before handing them out
)


# Enable WAL mode for SQLite for better concurrency
# This needs to be done for every connection
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute(
            "PRAGMA busy_timeout = 5000"
        )  # Set busy timeout to 5000ms (5 seconds)
        cursor.execute(
            "PRAGMA synchronous=NORMAL;"
        )  # Can relax synchronous setting slightly with WAL
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
