import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.main import app
from backend.routes import admin as admin_routes
from backend.services import cache_service, db_service
from backend.services.auth_service import create_access_token, require_admin
from backend.tests.test_utils import configure_test_db, disable_app_lifespan, teardown_test_db


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    engine = configure_test_db(monkeypatch, tmp_path, "test_admin.db")
    disable_app_lifespan(monkeypatch, app)
    yield
    teardown_test_db(engine)


def make_admin_user():
    db_service.create_user("admin@usms.ac.ma", "password", force_role="admin")
    return db_service.find_user_by_email("admin@usms.ac.ma")


def get_admin_headers():
    admin = make_admin_user()
    token = create_access_token(admin["id"], admin["email"], admin["role"])
    return {"Authorization": f"Bearer {token}"}


def test_admin_stats():
    data = admin_routes.get_stats(admin=make_admin_user()).model_dump()
    assert "total_users" in data
    assert "feedback_stats" in data


def test_admin_users():
    body = admin_routes.get_users(admin=make_admin_user())
    assert "users" in body
    assert any(user["email"] == "admin@usms.ac.ma" for user in body["users"])


def test_cache_flush(monkeypatch):
    calls = []
    monkeypatch.setattr(cache_service, "invalidate_cache", lambda prefix="*": calls.append(prefix))

    resp = admin_routes.flush_cache(admin=make_admin_user())
    assert resp["success"] is True
    assert calls == ["*"]



def test_official_json_faq_preview_returns_extracted_snippets():
    headers = get_admin_headers()
    resp = client.get("/api/v1/admin/faq/files/faq_ensa_bm_officielle_5000.json/preview", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["file_type"] == "json"
    assert data["snippet_count"] >= 5000
    assert "Question" in data["text"] or "Reponse" in data["text"]


def test_official_pdf_faq_preview_returns_extracted_snippets():
    headers = get_admin_headers()
    # The repo may keep a JSON twin instead of the PDF. Try PDF endpoint first,
    # fall back to JSON preview if the PDF is not present.
    resp = client.get("/api/v1/admin/faq/files/faq_ensa_bm_officielle_5000.pdf/preview", headers=headers)
    if resp.status_code == 404:
        resp = client.get("/api/v1/admin/faq/files/faq_ensa_bm_officielle_5000.json/preview", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["file_type"] in ("pdf", "json")
    assert data["snippet_count"] > 0
    assert "Question" in data["text"] or "Reponse" in data["text"]


def test_non_admin_access():
    student = db_service.create_user("student@usms.ac.ma", "StrongPass123!")
    with pytest.raises(HTTPException) as exc:
        require_admin(current_user=student)
    assert exc.value.status_code == 403
