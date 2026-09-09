import json

import pytest

from backend.scripts.seed_timetables import seed_timetables
from backend.services import db_service
from backend.tests.test_utils import configure_test_db, teardown_test_db


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    engine = configure_test_db(monkeypatch, tmp_path, "test_timetable_seed.db")
    yield
    teardown_test_db(engine)


def test_seed_timetables_imports_versioned_payload(tmp_path):
    seed_file = tmp_path / "timetables.json"
    seed_file.write_text(
        json.dumps(
            {
                "timetables": [
                    {
                        "class_label": "IACS_2025-2026_S4",
                        "academic_year": "2025-2026",
                        "semester": "S4",
                        "slots": [
                            {
                                "day_of_week": 0,
                                "start_time": "08:30",
                                "end_time": "10:15",
                                "subject": "Algo avancee",
                                "professor": "Pr. Test",
                                "room": "A1",
                                "type": "Cours",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = seed_timetables(seed_path=seed_file, replace=True)

    assert result["count"] == 1
    timetable = db_service.get_active_timetable("IACS_2025-2026_S4")
    assert timetable is not None
    assert timetable["slots"][0]["subject"] == "Algo avancee"
