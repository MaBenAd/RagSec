import asyncio
import io
import json
import subprocess
import sys

from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from attacks.pdf_fixtures import text_pdf
from rag.parser_app import app


def test_valid_pdf_and_worker_http():
    with TestClient(app) as client:
        result = client.post("/parse", content=text_pdf())
    assert result.status_code == 200
    assert "Library hours 09:00 to 17:00" in result.json()["text"]


def test_encrypted_pdf_is_rejected():
    writer = PdfWriter()
    writer.append_pages_from_reader(PdfReader(io.BytesIO(text_pdf())))
    writer.encrypt("synthetic-owned-pdf-password")
    output = io.BytesIO()
    writer.write(output)
    with TestClient(app) as client:
        assert client.post("/parse", content=output.getvalue()).status_code == 422


def test_extraction_expansion_is_rejected():
    with TestClient(app) as client:
        result = client.post("/parse", content=text_pdf("A" * 33000))
    assert result.status_code == 422
