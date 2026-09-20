from fastapi.testclient import TestClient
from backend.services.auth_service import create_access_token
from backend.services.db_service import User
from gateway.app import create_app


def test_logout_revokes_old_token(published):
    token = create_access_token(1, "user1@example.test", "student")
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(create_app(published.pipeline, published.ingestion, published.memories)) as client:
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_expired_token_denied(published):
    import jwt
    from backend.services.auth_service import SECRET_KEY
    token = jwt.encode({"sub": "1", "email": "user1@example.test", "role": "student", "exp": 1,
                        "type": "access", "access_version": 1}, SECRET_KEY, algorithm="HS256")
    with TestClient(create_app(published.pipeline, published.ingestion, published.memories)) as client:
        assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
