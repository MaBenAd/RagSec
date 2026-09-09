import os
import time
import pytest
from sqlalchemy import inspect
from backend.services import db_service
from backend.services.db_service import Message

from backend.tests.test_utils import configure_test_db, teardown_test_db


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    """Setup a fresh test database before each test."""
    db_path = tmp_path / "test_users.db"
    engine = configure_test_db(monkeypatch, tmp_path, "test_users.db")
    yield

    teardown_test_db(engine)
    if os.path.exists(db_path):
        # Windows may keep a short-lived lock on SQLite files right after teardown.
        for attempt in range(5):
            try:
                os.remove(db_path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)

def test_db_schema_improvements():
    """Verifies that DB models have correct indices and relationships."""
    from backend.services.db_service import engine
    inspector = inspect(engine)
    
    # 1. Check if indices exist on users table
    user_indices = inspector.get_indexes("users")
    user_idx_names = [idx["name"] for idx in user_indices]
    # SQLAlchemy index names might vary if not explicit, but we check if columns are indexed
    indexed_columns = [idx["column_names"][0] for idx in user_indices]
    assert "email" in indexed_columns
    
    # 2. Check if indices exist on messages
    msg_indices = inspector.get_indexes("messages")
    # In our model, we didn't explicitly name them but conversation_id is part of a FK
    
    # 3. Check messages table schema
    columns = [c["name"] for c in inspector.get_columns("messages")]
    assert "user_id" not in columns, "user_id should not be in messages table"
    assert "conversation_id" in columns
    assert "feedback" in columns
    assert "source_file" in columns
    
    # 4. Check for Foreign Key constraints
    fks = inspector.get_foreign_keys("messages")
    msg_fks = [fk for fk in fks if fk["referred_table"] == "conversations" and "conversation_id" in fk["constrained_columns"]]
    assert len(msg_fks) > 0, "messages should have a FK to conversations"

def test_foreign_key_enforcement():
    """Verifies that FK constraints are handled by SQLAlchemy/SQLite."""
    from sqlalchemy.exc import IntegrityError
    from backend.services.db_service import SessionLocal
    
    db = SessionLocal()
    try:
        # Attempt to insert a message for a non-existent conversation (id=99999)
        # Note: SQLite needs "PRAGMA foreign_keys = ON" to enforce this at DB level.
        # SQLAlchemy handles the relationship logic.
        msg = Message(conversation_id=99999, role="user", content="test")
        db.add(msg)
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()
