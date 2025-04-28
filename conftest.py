import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# --- Alembic Imports ---
from alembic.config import Config
from alembic import command
# --- End Alembic Imports ---

# Import app and DB dependency function first
from main import app, get_db

# Import database components needed for setup
from database import Base

TEST_DATABASE_URL = "sqlite:///./great-fit-test.db"

connect_args = (
    {"check_same_thread": False} if TEST_DATABASE_URL.startswith("sqlite") else {}
)
test_engine = create_engine(TEST_DATABASE_URL, connect_args=connect_args)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create the test database from models and stamp with Alembic head."""
    db_path = TEST_DATABASE_URL.split("///")[-1]
    if os.path.exists(db_path):
        try:
            os.unlink(db_path)
            print(f"\nRemoved existing test database file: {db_path}")
        except OSError as e:
            print(f"Error removing existing test database file {db_path}: {e}")

    print(f"Creating test database tables from models at {db_path}")
    # --- Create schema directly from models --- #
    Base.metadata.create_all(bind=test_engine)
    # --- End schema creation --- #

    print("Stamping database with Alembic head revision")
    # --- Stamp the database with the latest Alembic revision --- #
    alembic_cfg = Config("alembic.ini") # Load base config
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL) # Point to test DB
    command.stamp(alembic_cfg, "head") # Mark DB as up-to-date
    # --- End Alembic stamp --- #

    yield  # Tests run here

    test_engine.dispose()
    if os.path.exists(db_path):
        try:
            os.unlink(db_path)
            print(f"Removed test database file: {db_path}")
        except OSError as e:
            print(f"Error removing test database file {db_path}: {e}")


@pytest.fixture(scope="function") # Function scope for session
def db_session(setup_test_database): # Depends on DB setup
    """Yields a SQLAlchemy session directly from the test factory."""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


# Override the get_db dependency for tests
@pytest.fixture(scope="function")
def override_get_db():
    """Override the get_db dependency to use our test database.

    This creates a new session for each API call, allowing proper
    transaction handling within FastAPI endpoints.
    """

    def _override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    original = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db

    yield

    if original:
        app.dependency_overrides[get_db] = original
    else:
        del app.dependency_overrides[get_db]


@pytest.fixture(scope="function")
def test_client(override_get_db):
    """Provides a test client configured with our test database session."""
    return TestClient(app)
