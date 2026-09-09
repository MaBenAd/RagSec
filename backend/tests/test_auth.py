import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from backend.main import app
from backend.routes import auth as auth_routes
from backend.services import db_service
from backend.tests.test_utils import configure_test_db, disable_app_lifespan, teardown_test_db


TEST_EMAIL = "test.student@usms.ac.ma"
TEST_PASSWORD = "StrongPass123!"
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch, tmp_path):
    engine = configure_test_db(monkeypatch, tmp_path, "test_auth.db")
    disable_app_lifespan(monkeypatch, app)
    yield
    teardown_test_db(engine)


def test_register_and_login():
    response = Response()
    register_data = auth_routes.register(
        auth_routes.RegisterRequest(
            email=TEST_EMAIL,
            password=TEST_PASSWORD,
            class_label="IACS",
            language="en",
            accepted_privacy=True,
        ),
        response,
    ).model_dump()

    assert register_data["user"]["email"] == TEST_EMAIL
    assert register_data["user"]["language"] == "en"
    assert "access_token" in register_data

    login_data = auth_routes.login(
        auth_routes.LoginRequest(email=TEST_EMAIL, password=TEST_PASSWORD),
        Response(),
    ).model_dump()
    assert login_data["user"]["email"] == TEST_EMAIL


def test_invalid_email_domain():
    with pytest.raises(auth_routes.HTTPException) as exc:
        auth_routes.register(
            auth_routes.RegisterRequest(
                email="hacker@gmail.com",
                password=TEST_PASSWORD,
                accepted_privacy=True,
            ),
            Response(),
        )

    assert exc.value.status_code == 400
    assert "domaine" in exc.value.detail.lower()



def test_register_rejects_short_password():
    resp = client.post("/api/v1/auth/register", json={
        "email": "short.pass@usms.ac.ma",
        "password": "abc123",
        "accepted_privacy": True,
    })
    assert resp.status_code == 422
    assert "8" in resp.json()["detail"]

def test_update_language():
    register_data = auth_routes.register(
        auth_routes.RegisterRequest(
            email=TEST_EMAIL,
            password=TEST_PASSWORD,
            accepted_privacy=True,
        ),
        Response(),
    ).model_dump()
    current_user = {
        "id": register_data["user"]["id"],
        "email": register_data["user"]["email"],
        "role": register_data["user"]["role"],
    }

    result = auth_routes.update_language(
        auth_routes.LanguageUpdateRequest(language="ar"),
        current_user=current_user,
    )

    assert result["success"] is True
    assert db_service.find_user_by_email(TEST_EMAIL)["language"] == "ar"


def test_register_rejects_duplicate_email():
    payload = auth_routes.RegisterRequest(
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
        accepted_privacy=True,
    )

    auth_routes.register(payload, Response())
    with pytest.raises(auth_routes.HTTPException) as exc:
        auth_routes.register(payload, Response())

    assert exc.value.status_code == 409
    assert "existe" in exc.value.detail.lower()



def test_get_me_returns_current_user_profile():
    reg_resp = client.post("/api/v1/auth/register", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "accepted_privacy": True,
    })
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == TEST_EMAIL
    assert body["role"] == "student"


def test_cookie_session_and_csrf_protection():
    local_client = TestClient(app)

    reg_resp = local_client.post("/api/v1/auth/register", json={
        "email": "cookie.user@usms.ac.ma",
        "password": TEST_PASSWORD,
        "accepted_privacy": True,
    })
    assert reg_resp.status_code == 201
    assert local_client.cookies.get("access_token")
    assert local_client.cookies.get("csrf_token")

    me_resp = local_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "cookie.user@usms.ac.ma"

    blocked = local_client.post("/api/v1/auth/me/language", json={"language": "en"})
    assert blocked.status_code == 403

    csrf = local_client.cookies.get("csrf_token")
    allowed = local_client.post(
        "/api/v1/auth/me/language",
        json={"language": "en"},
        headers={"X-CSRF-Token": csrf},
    )
    assert allowed.status_code == 200

    logout_resp = local_client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    assert not local_client.cookies.get("access_token")


def test_refresh_cookie_returns_new_access_token():
    local_client = TestClient(app)

    reg_resp = local_client.post("/api/v1/auth/register", json={
        "email": "refresh.user@usms.ac.ma",
        "password": TEST_PASSWORD,
        "accepted_privacy": True,
    })
    assert reg_resp.status_code == 201
    assert local_client.cookies.get("refresh_token")

    refresh_resp = local_client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    body = refresh_resp.json()
    assert body["user"]["email"] == "refresh.user@usms.ac.ma"
    assert body["access_token"]

def test_get_my_timetable_resolves_canonical_class_label(monkeypatch):
    register_data = auth_routes.register(
        auth_routes.RegisterRequest(
            email=TEST_EMAIL,
            password=TEST_PASSWORD,
            class_label="IACS",
            accepted_privacy=True,
        ),
        Response(),
    ).model_dump()
    current_user = {
        "id": register_data["user"]["id"],
        "email": register_data["user"]["email"],
        "role": register_data["user"]["role"],
    }

    db_service.save_timetable(
        class_label="IACS_2025-2026_S4",
        academic_year="2025-2026",
        semester="S4",
        slots_data=[{
            "day_of_week": 0,
            "start_time": "08:30",
            "end_time": "10:00",
            "subject": "Analyse",
            "professor": "Pr. Test",
            "room": "A1",
            "type": "Cours",
        }],
    )

    monkeypatch.setattr(
        "backend.services.router_service.get_available_classes",
        lambda: {"IACS 2025-2026 S4": {"edt": "fake.json", "calendrier": None, "canonical_label": "IACS_2025-2026_S4"}},
    )

    timetable = auth_routes.get_my_timetable(current_user=current_user)["timetable"]
    assert timetable is not None
    assert timetable["class_label"] == "IACS_2025-2026_S4"
