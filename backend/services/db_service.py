"""
Service base de données — SQLAlchemy (PostgreSQL / SQLite)
Tables : users, conversations, messages, qa_review, class_change_requests
Admin MVP : admin@usms.ac.ma / password
"""
import os
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import List, Optional

import bcrypt

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Boolean,
    desc, select, update, delete, func, case, inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from sqlalchemy.sql import exists

from backend.services.logging_service import logger

# Configuration
_THIS_FILE = os.path.abspath(__file__)
_SERVICES_DIR = os.path.dirname(_THIS_FILE)  # backend/services/
_BACKEND_DIR = os.path.dirname(_SERVICES_DIR)  # backend/
DEFAULT_DB_PATH = os.path.join(_BACKEND_DIR, "data", "users.db")
ALEMBIC_INI_PATH = os.path.join(_BACKEND_DIR, "alembic.ini")
ALEMBIC_HEAD_REVISION = "20260920_0002"


def _utc_now() -> datetime:
    return datetime.now(UTC)

def normalize_database_url(url: str | None) -> str:
    candidate = url or f"sqlite:///{DEFAULT_DB_PATH}"
    if candidate.startswith("postgresql://"):
        return candidate.replace("postgresql://", "postgresql+pg8000://", 1)
    return candidate


def is_sqlite_url(url: str | None = None) -> bool:
    return normalize_database_url(url).startswith("sqlite")


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL"))

ADMIN_EMAIL = "admin@usms.ac.ma"
ADMIN_PASSWORD = (os.getenv("ADMIN_PASSWORD") or "").strip()

# Engine & Session
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if is_sqlite_url(DATABASE_URL) else {}
)

# Enable Foreign Keys for SQLite
if is_sqlite_url(DATABASE_URL):
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=True)
    role = Column(String(50), default="student")
    class_label = Column(String(120), nullable=True)
    language = Column(String(5), default="fr")
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utc_now)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    revision_plans = relationship("RevisionPlan", back_populates="user", cascade="all, delete-orphan")
    class_change_requests = relationship(
        "ClassChangeRequest",
        back_populates="user",
        foreign_keys="ClassChangeRequest.user_id",
        cascade="all, delete-orphan"
    )


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(255), default="Nouvelle discussion")
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    source_file = Column(String(255), nullable=True)
    feedback = Column(Integer, default=0)  # -1, 0, 1
    metadata_json = Column(Text, nullable=True) # JSON stored as string
    created_at = Column(DateTime, default=_utc_now)

    conversation = relationship("Conversation", back_populates="messages")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(100), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    timestamp = Column(DateTime, default=_utc_now)
    details = Column(Text, nullable=True)

    user = relationship("User")


class QAReview(Base):
    __tablename__ = "qa_review"
    id = Column(Integer, primary_key=True, index=True)
    question_hash = Column(String(64), unique=True, index=True, nullable=False)
    question = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    note = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)


class ClassChangeRequest(Base):
    __tablename__ = "class_change_requests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    current_class_label = Column(String(120), nullable=True)
    requested_class_label = Column(String(120), nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    review_note = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    user = relationship("User", back_populates="class_change_requests", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class Timetable(Base):
    __tablename__ = "timetables"
    id = Column(Integer, primary_key=True, index=True)
    class_label = Column(String(120), index=True, nullable=False)
    academic_year = Column(String(50), nullable=False)  # e.g. "2025-2026"
    semester = Column(String(10), nullable=False)       # e.g. "S4"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    slots = relationship("TimetableSlot", back_populates="timetable", cascade="all, delete-orphan")


class TimetableSlot(Base):
    __tablename__ = "timetable_slots"
    id = Column(Integer, primary_key=True, index=True)
    timetable_id = Column(Integer, ForeignKey("timetables.id", ondelete="CASCADE"), index=True, nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = Column(String(10), nullable=False) # "08:30"
    end_time = Column(String(10), nullable=False)   # "10:20"
    subject = Column(String(255), nullable=False)
    professor = Column(String(255), nullable=True)
    room = Column(String(100), nullable=True)
    type = Column(String(50), nullable=True)       # Cours, TD, TP

    timetable = relationship("Timetable", back_populates="slots")


class RevisionPlan(Base):
    __tablename__ = "revision_plans"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(160), nullable=False)
    modules_json = Column(Text, nullable=False)
    availability_json = Column(Text, nullable=False)
    sessions_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    user = relationship("User", back_populates="revision_plans")


# ─────────────────────────────────────────────────
# PASSWORDS
# ─────────────────────────────────────────────────

def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    return f"bcrypt${hashed}"


def _verify_legacy_password(stored: str, provided: str) -> bool:
    try:
        salt = bytes.fromhex(stored[:32])
        hash_val = stored[32:]
        computed = hashlib.sha256(salt + provided.encode("utf-8")).hexdigest()
        return hmac.compare_digest(computed, hash_val)
    except Exception:
        return False


def verify_password(stored: str, provided: str) -> bool:
    if not stored:
        return False
    try:
        if stored.startswith("bcrypt$"):
            return bcrypt.checkpw(provided.encode("utf-8"), stored.split("$", 1)[1].encode("utf-8"))
        if stored.startswith("$2a$") or stored.startswith("$2b$") or stored.startswith("$2y$"):
            return bcrypt.checkpw(provided.encode("utf-8"), stored.encode("utf-8"))
        return _verify_legacy_password(stored, provided)
    except ValueError:
        return False


def password_needs_rehash(stored: str | None) -> bool:
    if not stored:
        return False
    return not (
        stored.startswith("bcrypt$")
        or stored.startswith("$2a$")
        or stored.startswith("$2b$")
        or stored.startswith("$2y$")
    )


# ─────────────────────────────────────────────────
# SESSION CONTEXT MANAGER
# ─────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────────
# INIT / SEED
# ─────────────────────────────────────────────────

def _apply_legacy_sqlite_migrations():
    import sqlite3

    db_path = DATABASE_URL.replace("sqlite:///", "", 1)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(users)")
        user_columns = [column[1] for column in cursor.fetchall()]
        if "language" not in user_columns:
            logger.info("MIGRATION: Adding 'language' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN language VARCHAR(5) DEFAULT 'fr'")
        
        if "failed_login_attempts" not in user_columns:
            logger.info("MIGRATION: Adding 'failed_login_attempts' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0")
        
        if "locked_until" not in user_columns:
            logger.info("MIGRATION: Adding 'locked_until' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN locked_until DATETIME")

        cursor.execute("PRAGMA table_info(messages)")
        msg_columns = [column[1] for column in cursor.fetchall()]
        if "metadata_json" not in msg_columns:
            logger.info("MIGRATION: Adding 'metadata_json' column to 'messages' table.")
            cursor.execute("ALTER TABLE messages ADD COLUMN metadata_json TEXT")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS revision_plans (
                id INTEGER NOT NULL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title VARCHAR(160) NOT NULL,
                modules_json TEXT NOT NULL,
                availability_json TEXT NOT NULL,
                sessions_json TEXT NOT NULL,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_revision_plans_user_id ON revision_plans (user_id)")

        conn.commit()
    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise
    finally:
        conn.close()


def _run_postgres_migrations():
    from alembic import command

    config = _get_alembic_config()
    command.upgrade(config, "head")


def _get_alembic_config():
    from alembic.config import Config

    config = Config(ALEMBIC_INI_PATH)
    config.set_main_option("script_location", os.path.join(_BACKEND_DIR, "alembic"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    return config


def _bootstrap_legacy_postgres_schema() -> bool:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if not existing_tables or "alembic_version" in existing_tables:
        return False

    logger.info("Detected legacy PostgreSQL schema without Alembic metadata; bootstrapping compatibility changes.")
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        refreshed = inspect(connection)

        if "users" in existing_tables:
            user_columns = {column["name"] for column in refreshed.get_columns("users")}
            if "language" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN language VARCHAR(5) DEFAULT 'fr'"))

        if "messages" in existing_tables:
            message_columns = {column["name"] for column in refreshed.get_columns("messages")}
            if "metadata_json" not in message_columns:
                connection.execute(text("ALTER TABLE messages ADD COLUMN metadata_json TEXT"))

    from alembic import command

    command.stamp(_get_alembic_config(), ALEMBIC_HEAD_REVISION)
    return True


def init_db():
    if is_sqlite_url(DATABASE_URL):
        os.makedirs(os.path.dirname(DEFAULT_DB_PATH), exist_ok=True)
        Base.metadata.create_all(bind=engine)
        _apply_legacy_sqlite_migrations()
        return

    if _bootstrap_legacy_postgres_schema():
        return

    _run_postgres_migrations()


def seed_admin():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not admin:
            if not ADMIN_PASSWORD:
                logger.warning("ADMIN_PASSWORD is not set; skipping automatic admin seeding.")
                return
            if len(ADMIN_PASSWORD) < 12:
                logger.warning("ADMIN_PASSWORD is too short (<12); skipping automatic admin seeding.")
                return
            pwd_hash = hash_password(ADMIN_PASSWORD)
            new_admin = User(
                email=ADMIN_EMAIL,
                password=pwd_hash,
                role="admin",
                class_label=None
            )
            db.add(new_admin)
            db.commit()
            logger.info("✅ Admin user seeded.")
    except Exception as e:
        logger.error(f"Error seeding admin: {e}")
    finally:
        db.close()


# ─────────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────────

def create_user(
    email: str,
    password: str | None = None,
    class_label: str | None = None,
    force_role: str | None = None,
    language: str = "fr",
) -> dict | None:
    role = force_role or ("admin" if email == ADMIN_EMAIL else "student")
    pwd_hash = hash_password(password) if password else None
    
    db = SessionLocal()
    try:
        new_user = User(
            email=email,
            password=pwd_hash,
            role=role,
            class_label=class_label,
            language=language
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return _to_dict(new_user)
    except Exception as e:
        logger.error(f"Error creating user {email}: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def find_user_by_email(email: str) -> dict | None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        return _to_dict(user)
    finally:
        db.close()


def get_user_by_id(user_id: int) -> dict | None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        return _to_dict(user)
    finally:
        db.close()


def verify_user(email: str, password: str) -> dict | None:
    """Vérifie les identifiants et gère la politique de verrouillage (Brute-force)."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email.strip().lower()).first()
        if not user:
            return None
        
        # Vérification verrouillage
        if user.locked_until and user.locked_until > _utc_now():
            logger.warning(f"Login attempt on locked account: {email}")
            return {"locked": True, "until": user.locked_until}

        if user.password and verify_password(user.password, password):
            # Succès : Reset des tentatives
            user.failed_login_attempts = 0
            user.locked_until = None
            if password_needs_rehash(user.password):
                try:
                    user.password = hash_password(password)
                except Exception as e:
                    logger.warning(f"Password rehash skipped for {email}: {e}")
            db.commit()
            return _to_dict(user)
        else:
            # Échec : Incrémenter
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= 5:
                user.locked_until = _utc_now() + timedelta(minutes=30)
                log_audit_action("account_locked", user.id, details=f"Too many failed attempts for {email}")
            db.commit()
            return None
    finally:
        db.close()


def update_user_class(user_id: int, class_label: str | None):
    db = SessionLocal()
    try:
        db.execute(
            update(User).where(User.id == user_id).values(class_label=class_label)
        )
        db.commit()
    finally:
        db.close()


def update_user_language(user_id: int, language: str):
    db = SessionLocal()
    try:
        db.execute(
            update(User).where(User.id == user_id).values(language=language)
        )
        db.commit()
    finally:
        db.close()


def get_all_users() -> list:
    db = SessionLocal()
    try:
        users = db.query(User).order_by(desc(User.created_at)).all()
        return [_to_dict(u) for u in users]
    finally:
        db.close()


# ─────────────────────────────────────────────────
# CONVERSATIONS
# ─────────────────────────────────────────────────

def create_conversation(user_id: int, title: str = "Nouvelle discussion") -> int:
    db = SessionLocal()
    try:
        conv = Conversation(user_id=user_id, title=title)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv.id
    except Exception as e:
        logger.error(f"Error creating conversation for user_id={user_id}: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def get_conversations(user_id: int) -> list:
    db = SessionLocal()
    try:
        convs = db.query(Conversation)\
                  .filter(Conversation.user_id == user_id)\
                  .order_by(desc(Conversation.updated_at))\
                  .limit(30)\
                  .all()
        return [_to_dict(c) for c in convs]
    finally:
        db.close()


def get_total_conversations() -> int:
    db = SessionLocal()
    try:
        return db.query(func.count(Conversation.id)).scalar() or 0
    finally:
        db.close()


def update_conversation_title(conv_id: int, title: str):
    db = SessionLocal()
    try:
        db.execute(
            update(Conversation).where(Conversation.id == conv_id).values(title=title)
        )
        db.commit()
    finally:
        db.close()


def delete_conversation(conv_id: int):
    db = SessionLocal()
    try:
        db.execute(delete(Conversation).where(Conversation.id == conv_id))
        db.commit()
    finally:
        db.close()


# ─────────────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────────────

def add_message(conv_id: int, role: str, content: str, source_file: str | None = None, metadata: dict | None = None):
    db = SessionLocal()
    try:
        import json
        msg = Message(
            conversation_id=conv_id,
            role=role,
            content=content,
            source_file=source_file,
            metadata_json=json.dumps(metadata) if metadata else None
        )
        db.add(msg)
        # Update conversation timestamp
        db.execute(
            update(Conversation).where(Conversation.id == conv_id).values(updated_at=_utc_now())
        )
        db.commit()
    except Exception as e:
        logger.error(f"Error adding message for conversation_id={conv_id}: {e}")
        db.rollback()
    finally:
        db.close()


def update_message_feedback(message_id: int, feedback: int):
    db = SessionLocal()
    try:
        db.execute(
            update(Message).where(Message.id == message_id).values(feedback=feedback)
        )
        db.commit()
    finally:
        db.close()


def conversation_belongs_to_user(conv_id: int, user_id: int) -> bool:
    db = SessionLocal()
    try:
        exists_row = db.query(Conversation.id).filter(
            Conversation.id == conv_id,
            Conversation.user_id == user_id,
        ).first()
        return exists_row is not None
    finally:
        db.close()


def message_belongs_to_user(message_id: int, user_id: int) -> bool:
    db = SessionLocal()
    try:
        exists_row = db.query(Message.id).join(
            Conversation,
            Message.conversation_id == Conversation.id,
        ).filter(
            Message.id == message_id,
            Conversation.user_id == user_id,
        ).first()
        return exists_row is not None
    finally:
        db.close()


def get_messages(conv_id: int, limit: int = 200) -> list:
    db = SessionLocal()
    try:
        msgs = db.query(Message)\
                 .filter(Message.conversation_id == conv_id)\
                 .order_by(Message.id.desc())\
                 .limit(limit)\
                 .all()
        msgs.reverse()
        return [_to_dict(m) for m in msgs]
    finally:
        db.close()


def get_total_messages() -> int:
    db = SessionLocal()
    try:
        return db.query(func.count(Message.id)).scalar() or 0
    finally:
        db.close()


# ─────────────────────────────────────────────────
# ADMIN — analytics
# ─────────────────────────────────────────────────

def get_all_qa_pairs(limit: int = 100) -> list:
    db = SessionLocal()
    try:
        # Complex join for Q&A pairs
        user_msgs = db.query(Message, User.email, Conversation.id)\
                      .join(Conversation, Message.conversation_id == Conversation.id)\
                      .join(User, Conversation.user_id == User.id)\
                      .filter(Message.role == 'user')\
                      .order_by(desc(Message.created_at))\
                      .limit(limit)\
                      .all()
        
        results = []
        for u_msg, email, cid in user_msgs:
            a_msg = db.query(Message)\
                      .filter(Message.conversation_id == cid)\
                      .filter(Message.role == 'assistant')\
                      .filter(Message.id > u_msg.id)\
                      .order_by(Message.id.asc())\
                      .first()
            if a_msg:
                results.append({
                    "question": u_msg.content,
                    "answer": a_msg.content,
                    "feedback": a_msg.feedback,
                    "user_email": email,
                    "created_at": u_msg.created_at.isoformat() if u_msg.created_at else ""
                })
        return results
    finally:
        db.close()


def get_top_questions(limit: int = 5) -> list:
    db = SessionLocal()
    try:
        counts = db.query(func.lower(func.trim(Message.content)).label("question_norm"), func.count("*").label("cnt"))\
                   .filter(Message.role == 'user')\
                   .group_by("question_norm")\
                   .order_by(desc("cnt"))\
                   .limit(limit)\
                   .all()
        return [{"question": r[0], "count": r[1]} for r in counts]
    finally:
        db.close()


def get_weak_questions_grouped(limit: int = 30) -> list:
    weak_markers = [
        "je ne trouve pas", "aucune information", "pas trouvé",
        "❌", "aucun cours", "je n'ai pas encore d'information fiable",
    ]
    pairs = get_all_qa_pairs(limit=2000)
    grouped = {}
    for p in pairs:
        q = (p.get("question") or "").strip()
        r = (p.get("answer") or "").lower()
        if not q: continue
        if not any(m in r for m in weak_markers): continue
        
        key = q.lower().strip()
        if key not in grouped:
            grouped[key] = {
                "question": q,
                "occurrences": 0,
                "last_seen": p.get("created_at") or "",
            }
        grouped[key]["occurrences"] += 1
        if (p.get("created_at") or "") > grouped[key]["last_seen"]:
            grouped[key]["last_seen"] = p.get("created_at") or ""
            
    rows = list(grouped.values())
    rows.sort(key=lambda x: (-x["occurrences"], x["question"]))
    return rows[:limit]


def set_question_review_status(question: str, status: str = "pending", note: str | None = None):
    q = (question or "").strip()
    if not q: return
    q_hash = hashlib.sha256(q.lower().encode("utf-8")).hexdigest()
    
    db = SessionLocal()
    try:
        review = db.query(QAReview).filter(QAReview.question_hash == q_hash).first()
        if review:
            review.question = q
            review.status = status
            review.note = note
            review.updated_at = _utc_now()
        else:
            new_review = QAReview(
                question_hash=q_hash,
                question=q,
                status=status,
                note=note
            )
            db.add(new_review)
        db.commit()
    finally:
        db.close()


def get_question_review_statuses() -> dict:
    db = SessionLocal()
    try:
        reviews = db.query(QAReview).all()
        return {r.question_hash: r.status for r in reviews}
    finally:
        db.close()


def get_feedback_stats() -> dict:
    db = SessionLocal()
    try:
        pos = db.query(func.count(Message.id)).filter(Message.feedback == 1).scalar() or 0
        neg = db.query(func.count(Message.id)).filter(Message.feedback == -1).scalar() or 0
        return {"positive": pos, "negative": neg}
    finally:
        db.close()


def get_users_activity(email_query: str = "", limit: int = 200) -> list:
    db = SessionLocal()
    try:
        query = db.query(
            User.id, User.email, User.role, User.class_label, User.created_at,
            func.count(func.distinct(Conversation.id)).label("conv_count"),
            func.count(Message.id).label("msg_count")
        ).outerjoin(Conversation, User.id == Conversation.user_id)\
         .outerjoin(Message, Conversation.id == Message.conversation_id)\
         .group_by(User.id)
        
        if email_query.strip():
            query = query.filter(User.email.ilike(f"%{email_query.strip()}%"))
            
        rows = query.order_by(desc("msg_count"), desc("conv_count")).limit(limit).all()
        
        return [{
            "id": r[0], "email": r[1], "role": r[2], "class_label": r[3],
            "created_at": r[4].isoformat() if r[4] else "",
            "conversations_count": r[5], "messages_count": r[6]
        } for r in rows]
    finally:
        db.close()


# ─────────────────────────────────────────────────
# CLASS CHANGE REQUESTS
# ─────────────────────────────────────────────────

def create_class_change_request(user_id: int, requested_class_label: str, reason: str | None = None) -> dict | None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user: return None
        
        requested = (requested_class_label or "").strip()
        if not requested or (user.class_label or "").strip().lower() == requested.lower():
            return None
            
        existing = db.query(ClassChangeRequest)\
                     .filter(ClassChangeRequest.user_id == user_id, ClassChangeRequest.status == 'pending')\
                     .first()
        if existing:
            return {"id": existing.id, "status": "pending_existing"}
            
        req = ClassChangeRequest(
            user_id=user_id,
            current_class_label=user.class_label,
            requested_class_label=requested,
            reason=(reason or "").strip() or None
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return _to_dict(req)
    finally:
        db.close()


def get_class_change_requests(status: str | None = None, user_id: int | None = None) -> list:
    db = SessionLocal()
    try:
        query = db.query(ClassChangeRequest, User.email).join(User, ClassChangeRequest.user_id == User.id)
        
        if status:
            query = query.filter(ClassChangeRequest.status == status)
        if user_id is not None:
            query = query.filter(ClassChangeRequest.user_id == user_id)
            
        results = query.order_by(
            case(
                (ClassChangeRequest.status == 'pending', 0),
                (ClassChangeRequest.status == 'approved', 1),
                else_=2
            ),
            desc(ClassChangeRequest.updated_at)
        ).all()
        
        output = []
        for req, email in results:
            d = _to_dict(req)
            d["user_email"] = email
            output.append(d)
        return output
    finally:
        db.close()


def decide_class_change_request(request_id: int, admin_id: int, decision: str, note: str | None = None) -> dict | None:
    decision = (decision or "").strip().lower()
    if decision not in {"approve", "reject"}: return None
    
    db = SessionLocal()
    try:
        req = db.query(ClassChangeRequest).filter(ClassChangeRequest.id == request_id).first()
        if not req: return None
        if req.status != "pending": return {"id": request_id, "status": "already_processed"}
        
        new_status = "approved" if decision == "approve" else "rejected"
        req.status = new_status
        req.review_note = (note or "").strip() or None
        req.reviewed_by = admin_id
        req.updated_at = _utc_now()
        
        if new_status == "approved":
            db.execute(
                update(User).where(User.id == req.user_id).values(class_label=req.requested_class_label)
            )
            
        db.commit()
        db.refresh(req)
        
        user_email = db.query(User.email).filter(User.id == req.user_id).scalar()
        d = _to_dict(req)
        d["user_email"] = user_email
        return d
    finally:
        db.close()


# ─────────────────────────────────────────────────
# TIMETABLES
# ─────────────────────────────────────────────────

def save_timetable(
    class_label: str,
    academic_year: str,
    semester: str,
    slots_data: list[dict]
) -> int:
    """
    Sauvegarde un emploi du temps complet. 
    Désactive les anciens emplois du temps pour cette classe/semestre.
    """
    db = SessionLocal()
    try:
        # Désactiver les versions précédentes
        db.execute(
            update(Timetable)
            .where(Timetable.class_label == class_label)
            .where(Timetable.semester == semester)
            .values(is_active=False)
        )

        # Créer le nouvel emploi du temps et les créneaux en une seule transaction
        new_tt = Timetable(
            class_label=class_label,
            academic_year=academic_year,
            semester=semester,
            is_active=True
        )
        db.add(new_tt)
        db.flush()  # Obtenir l'ID sans committer

        # Ajouter les créneaux
        slots_to_add = []
        for s in slots_data:
            slot = TimetableSlot(
                timetable_id=new_tt.id,
                day_of_week=s.get("day_of_week"),
                start_time=s.get("start_time"),
                end_time=s.get("end_time"),
                subject=s.get("subject"),
                professor=s.get("professor"),
                room=s.get("room"),
                type=s.get("type")
            )
            slots_to_add.append(slot)
        
        db.add_all(slots_to_add)
        db.commit()
        return new_tt.id
    except Exception as e:
        logger.error(f"Error saving timetable for {class_label}: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def get_active_timetable(class_label: str) -> dict | None:
    """Retourne l'emploi du temps actif pour une classe avec tous ses créneaux."""
    db = SessionLocal()
    try:
        tt = db.query(Timetable)\
               .filter(Timetable.class_label == class_label, Timetable.is_active == True)\
               .first()
        if not tt:
            return None
        
        result = _to_dict(tt)
        slots = db.query(TimetableSlot).filter(TimetableSlot.timetable_id == tt.id).all()
        result["slots"] = [_to_dict(s) for s in slots]
        return result
    finally:
        db.close()


def get_timetable_by_id(timetable_id: int, active_only: bool = True) -> dict | None:
    """Retourne un emploi du temps par id avec ses créneaux."""
    db = SessionLocal()
    try:
        query = db.query(Timetable).filter(Timetable.id == timetable_id)
        if active_only:
            query = query.filter(Timetable.is_active == True)

        tt = query.first()
        if not tt:
            return None

        result = _to_dict(tt)
        slots = db.query(TimetableSlot).filter(TimetableSlot.timetable_id == tt.id).all()
        result["slots"] = [_to_dict(s) for s in slots]
        return result
    finally:
        db.close()


def list_active_timetables() -> list[dict]:
    """Retourne tous les emplois du temps actifs avec leurs métadonnées principales."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Timetable)
            .filter(Timetable.is_active == True)
            .order_by(Timetable.class_label.asc(), Timetable.updated_at.desc())
            .all()
        )
        return [_to_dict(row) for row in rows]
    finally:
        db.close()


def delete_timetable(timetable_id: int) -> bool:
    """Supprime un emploi du temps (et ses créneaux via cascade)."""
    db = SessionLocal()
    try:
        row = db.query(Timetable).filter(Timetable.id == timetable_id).first()
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Error deleting timetable {timetable_id}: {e}")
        db.rollback()
        return False
    finally:
        db.close()


# ─────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────

def _revision_plan_to_dict(plan: RevisionPlan) -> dict:
    payload = _to_dict(plan)
    for json_field, public_field in [
        ("modules_json", "modules"),
        ("availability_json", "availability"),
        ("sessions_json", "sessions"),
    ]:
        raw = payload.pop(json_field, "[]")
        try:
            payload[public_field] = json.loads(raw or "[]")
        except Exception:
            payload[public_field] = []
    return payload


def list_revision_plans(user_id: int) -> list[dict]:
    db = SessionLocal()
    try:
        plans = (
            db.query(RevisionPlan)
            .filter(RevisionPlan.user_id == user_id)
            .order_by(RevisionPlan.updated_at.desc(), RevisionPlan.id.desc())
            .all()
        )
        return [_revision_plan_to_dict(plan) for plan in plans]
    finally:
        db.close()


def create_revision_plan(
    user_id: int,
    title: str,
    modules: list[dict],
    availability: list[dict],
    sessions: list[dict],
) -> dict | None:
    db = SessionLocal()
    try:
        now = _utc_now()
        plan = RevisionPlan(
            user_id=user_id,
            title=title,
            modules_json=json.dumps(modules, ensure_ascii=False),
            availability_json=json.dumps(availability, ensure_ascii=False),
            sessions_json=json.dumps(sessions, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        return _revision_plan_to_dict(plan)
    except Exception as e:
        logger.error(f"Error creating revision plan for user {user_id}: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def delete_revision_plan(plan_id: int, user_id: int) -> bool:
    db = SessionLocal()
    try:
        result = db.execute(
            delete(RevisionPlan).where(
                RevisionPlan.id == plan_id,
                RevisionPlan.user_id == user_id,
            )
        )
        db.commit()
        return bool(result.rowcount if result is not None else 0)
    finally:
        db.close()


def get_user_activity_graph(user_id: int, days: int = 30) -> list:
    """Retourne le nombre de messages par jour pour un utilisateur donné."""
    db = SessionLocal()
    try:
        # SQLite vs PostgreSQL date grouping
        if is_sqlite_url(DATABASE_URL):
            date_func = func.strftime("%Y-%m-%d", Message.created_at)
        else:
            date_func = func.to_char(Message.created_at, "YYYY-MM-DD")

        cutoff = _utc_now() - timedelta(days=max(days, 0))
        results = db.query(date_func.label("day"), func.count(Message.id).label("count"))\
                    .join(Conversation, Message.conversation_id == Conversation.id)\
                    .filter(Conversation.user_id == user_id)\
                    .filter(Message.created_at >= cutoff)\
                    .group_by("day")\
                    .order_by("day")\
                    .all()
        
        return [{"day": r[0], "count": r[1]} for r in results]
    finally:
        db.close()


def delete_user(user_id: int) -> bool:
    """Supprime un utilisateur et toutes ses données associées (cascade)."""
    db = SessionLocal()
    try:
        result = db.execute(delete(User).where(User.id == user_id))
        deleted = result.rowcount if result is not None else 0
        db.commit()
        return bool(deleted)
    finally:
        db.close()
        
def log_audit_action(action: str, user_id: int | None = None, details: str | None = None):
    """
    Log une action dans l'AuditLog pour la traçabilité et l'accountability (RGPD).
    """
    db = SessionLocal()
    try:
        log_entry = AuditLog(
            action=action,
            user_id=user_id,
            details=details
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Error logging audit action: {e}")
        db.rollback()
    finally:
        db.close()

def delete_all_conversations(user_id: int):
    """Supprime toutes les conversations d'un utilisateur (Droit à l'oubli)."""
    db = SessionLocal()
    try:
        db.execute(delete(Conversation).where(Conversation.user_id == user_id))
        db.commit()
    finally:
        db.close()

def cleanup_old_conversations(days: int = 180) -> int:
    """
    Supprime les conversations plus vieilles que X jours (Storage Limitation RGPD).
    Retourne le nombre de conversations supprimées.
    """
    db = SessionLocal()
    try:
        cutoff = _utc_now() - timedelta(days=days)
        # On récupère les IDs pour le log audit
        old_convs = db.execute(
            select(Conversation.id).where(Conversation.created_at < cutoff)
        ).scalars().all()
        
        count = len(old_convs)
        if count > 0:
            db.execute(delete(Conversation).where(Conversation.created_at < cutoff))
            db.commit()
            log_audit_action("automatic_cleanup", details=f"Deleted {count} conversations older than {days} days.")
        
        return count
    finally:
        db.close()

def _to_dict(obj):
    if obj is None: return None
    if isinstance(obj, dict): return obj
    
    d = {}
    for column in obj.__table__.columns:
        val = getattr(obj, column.name)
        if column.name == "metadata_json" and val:
            try:
                import json
                d["metadata"] = json.loads(val)
            except Exception:
                d["metadata"] = None
        elif isinstance(val, datetime):
            d[column.name] = val.isoformat()
        else:
            d[column.name] = val
    return d
