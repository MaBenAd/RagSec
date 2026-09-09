from backend import main
from backend.services import groq_service, rag_service


def test_health_check(monkeypatch):
    monkeypatch.setattr(rag_service, "get_collection", lambda: ("faq_campus", "local"))
    monkeypatch.setattr(groq_service, "get_client", lambda: object())

    body = main.health()

    assert body["version"] == "2.0.0"
    assert body["docs"] == "/docs"
    assert body["status"] == "ok"
    assert body["qdrant"] == "connected"
    assert body["groq"] == "connected"


def test_health_check_reports_partial_error(monkeypatch):
    def _raise_qdrant():
        raise RuntimeError("qdrant offline")

    monkeypatch.setattr(rag_service, "get_collection", _raise_qdrant)
    monkeypatch.setattr(groq_service, "get_client", lambda: object())

    body = main.health()

    assert body["status"] == "partial_error"
    assert body["groq"] == "connected"
    assert "qdrant offline" in body["qdrant"]
