from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DEFAULT_SOURCE_URL = "sqlite:///./backend/data/users.db"
DEFAULT_OUTPUT_PATH = Path("backend/data/seeds/timetables.json")


def _sqlite_path_from_url(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("This export script only supports sqlite:/// URLs.")
    return Path(database_url.replace(prefix, "", 1)).resolve()


def export_timetables(
    source_url: str = DEFAULT_SOURCE_URL,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    include_inactive: bool = False,
) -> dict:
    db_path = _sqlite_path_from_url(source_url)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        timetable_sql = """
            SELECT id, class_label, academic_year, semester, is_active, created_at, updated_at
            FROM timetables
        """
        if not include_inactive:
            timetable_sql += " WHERE is_active = 1"
        timetable_sql += " ORDER BY class_label, semester, id"
        cur.execute(timetable_sql)
        timetable_rows = cur.fetchall()

        timetables = []
        for timetable in timetable_rows:
            cur.execute(
                """
                SELECT day_of_week, start_time, end_time, subject, professor, room, type
                FROM timetable_slots
                WHERE timetable_id = ?
                ORDER BY day_of_week, start_time, id
                """,
                (timetable["id"],),
            )
            slots = [dict(slot) for slot in cur.fetchall()]
            timetables.append(
                {
                    "class_label": timetable["class_label"],
                    "academic_year": timetable["academic_year"],
                    "semester": timetable["semester"],
                    "is_active": bool(timetable["is_active"]),
                    "created_at": timetable["created_at"],
                    "updated_at": timetable["updated_at"],
                    "slots": slots,
                }
            )

        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "source": db_path.name,
            "include_inactive": include_inactive,
            "timetables": timetables,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export timetables from SQLite to a versioned JSON seed.")
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL, help="SQLite source URL.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Destination JSON file.",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include inactive timetable versions in the export.",
    )
    args = parser.parse_args()

    payload = export_timetables(
        source_url=args.source_url,
        output_path=Path(args.output),
        include_inactive=args.include_inactive,
    )
    print(
        f"Exported {len(payload['timetables'])} timetable(s) "
        f"to {Path(args.output).resolve()}"
    )


if __name__ == "__main__":
    main()
