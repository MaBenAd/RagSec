import pytest

from backend.services import cache_service, db_service


@pytest.fixture(autouse=True)
def _stub_password_hashing(monkeypatch):
    monkeypatch.setattr(db_service, "hash_password", lambda password: f"test-hash::{password}")
    monkeypatch.setattr(
        db_service,
        "verify_password",
        lambda stored, provided: stored == f"test-hash::{provided}",
    )
    monkeypatch.setattr(db_service, "password_needs_rehash", lambda _stored: False)


@pytest.fixture(autouse=True)
def _disable_redis_cache(monkeypatch):
    monkeypatch.setattr(cache_service, "CACHE_ENABLED", False)
    monkeypatch.setattr(cache_service, "_REDIS_CLIENT", None)
