from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")
from sqlalchemy import delete

from backend.services import db_service


DEFAULT_SEED_PATH = Path("backend/data/seeds/timetables.json")


def load_seed_payload(seed_path: Path = DEFAULT_SEED_PATH) -> dict:
    return json.loads(seed_path.read_text(encoding="utf-8"))


def seed_timetables(seed_path: Path = DEFAULT_SEED_PATH, replace: bool = False) -> dict:
    db_service.init_db()
    db_service.seed_admin()

    payload = load_seed_payload(seed_path)
    timetables = payload.get("timetables", [])

    if replace:
        db = db_service.SessionLocal()
        try:
            db.execute(delete(db_service.TimetableSlot))
            db.execute(delete(db_service.Timetable))
            db.commit()
        finally:
            db.close()

    for timetable in timetables:
        db_service.save_timetable(
            class_label=timetable["class_label"],
            academic_year=timetable["academic_year"],
            semester=timetable["semester"],
            slots_data=timetable.get("slots", []),
        )

    return {
        "seed_path": str(seed_path.resolve()),
        "count": len(timetables),
        "replace": replace,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed PostgreSQL with versioned timetable data.")
    parser.add_argument(
        "--input",
        default=str(DEFAULT_SEED_PATH),
        help="JSON seed file to import.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing timetable data before import.",
    )
    args = parser.parse_args()

    result = seed_timetables(seed_path=Path(args.input), replace=args.replace)
    print(
        f"Seeded {result['count']} timetable(s) from {result['seed_path']} "
        f"(replace={result['replace']})"
    )


if __name__ == "__main__":
    main()
