from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

from backend.scripts.seed_timetables import DEFAULT_SEED_PATH, seed_timetables
from backend.services import db_service
from backend.services.logging_service import logger
from backend.services.rag_service import (
    FAQ_DIR,
    _collection_count,
    _get_qdrant_client,
    rebuild_vectorstore,
)


def _sync_demo_accounts() -> None:
    accounts = []
    admin_password = (os.getenv("ADMIN_PASSWORD") or "").strip()
    if admin_password:
        accounts.append((db_service.ADMIN_EMAIL, admin_password, "admin", None))

    demo_email = (os.getenv("DEMO_STUDENT_EMAIL") or "").strip().lower()
    demo_password = (os.getenv("DEMO_STUDENT_PASSWORD") or "").strip()
    demo_class = (os.getenv("DEMO_STUDENT_CLASS") or "IACS_2025-2026_S4").strip()
    if demo_email and demo_password:
        accounts.append((demo_email, demo_password, "student", demo_class))

    if not accounts:
        return

    db = db_service.SessionLocal()
    try:
        for email, password, role, class_label in accounts:
            user = db.query(db_service.User).filter(db_service.User.email == email).first()
            password_hash = db_service.hash_password(password)
            if user:
                user.password = password_hash
                user.role = role
                user.failed_login_attempts = 0
                user.locked_until = None
                if class_label and not user.class_label:
                    user.class_label = class_label
            else:
                db.add(
                    db_service.User(
                        email=email,
                        password=password_hash,
                        role=role,
                        class_label=class_label,
                        language="fr",
                        failed_login_attempts=0,
                        locked_until=None,
                    )
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _faq_files_exist() -> bool:
    faq_dir = Path(FAQ_DIR)
    return faq_dir.exists() and any(path.is_file() and not path.name.startswith(".") for path in faq_dir.iterdir())


def _safe_close_qdrant_client(client: object | None) -> None:
    close_method = getattr(client, "close", None)
    if callable(close_method):
        try:
            close_method()
        except Exception as exc:
            logger.debug(f"Unable to close Qdrant client cleanly: {exc}")


def bootstrap_dev_content(seed_timetables_if_empty: bool = True, build_faq_if_empty: bool = True) -> dict:
    db_service.init_db()
    db_service.seed_admin()
    _sync_demo_accounts()

    result = {
        "timetables_seeded": False,
        "faq_rebuilt": False,
        "timetables_count": 0,
        "faq_chunks": 0,
        "faq_error": None,
    }

    db = db_service.SessionLocal()
    try:
        timetable_count = db.query(db_service.Timetable).count()
    finally:
        db.close()
    result["timetables_count"] = timetable_count

    if seed_timetables_if_empty and timetable_count == 0 and DEFAULT_SEED_PATH.exists():
        seed_result = seed_timetables(seed_path=DEFAULT_SEED_PATH, replace=False)
        result["timetables_seeded"] = seed_result["count"] > 0
        result["timetables_count"] = seed_result["count"]

    client = None
    rebuilt_client = None
    try:
        client = _get_qdrant_client()
        faq_chunks = _collection_count(client)
        result["faq_chunks"] = faq_chunks
        if build_faq_if_empty and faq_chunks == 0 and _faq_files_exist():
            rebuilt_client, _ = rebuild_vectorstore()
            result["faq_rebuilt"] = True
            result["faq_chunks"] = _collection_count(rebuilt_client)
    except Exception as exc:
        result["faq_error"] = str(exc)
    finally:
        _safe_close_qdrant_client(rebuilt_client)
        _safe_close_qdrant_client(client)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap local shared dev content (PostgreSQL + Qdrant) without duplicating data."
    )
    parser.add_argument(
        "--skip-timetables",
        action="store_true",
        help="Do not seed timetables even if the table is empty.",
    )
    parser.add_argument(
        "--skip-faq",
        action="store_true",
        help="Do not rebuild the FAQ vectorstore even if Qdrant is empty.",
    )
    args = parser.parse_args()

    result = bootstrap_dev_content(
        seed_timetables_if_empty=not args.skip_timetables,
        build_faq_if_empty=not args.skip_faq,
    )
    print(
        "Bootstrap complete: "
        f"timetables_seeded={result['timetables_seeded']}, "
        f"timetables_count={result['timetables_count']}, "
        f"faq_rebuilt={result['faq_rebuilt']}, "
        f"faq_chunks={result['faq_chunks']}, "
        f"faq_error={result['faq_error']}"
    )


if __name__ == "__main__":
    main()
