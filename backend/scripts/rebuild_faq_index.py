from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

from backend.services.rag_service import get_faq_status, rebuild_vectorstore
from backend.services.logging_service import logger


def _safe_close_qdrant_client(client: object | None) -> None:
    close_method = getattr(client, "close", None)
    if callable(close_method):
        try:
            close_method()
        except Exception as exc:
            logger.debug(f"Unable to close Qdrant client cleanly: {exc}")


def main() -> None:
    client, collection_name = rebuild_vectorstore()
    try:
        status = get_faq_status()
        print(
            f"Rebuilt FAQ vectorstore '{collection_name}' with "
            f"{status.get('total_chunks', 0)} chunks from {len(status.get('files', []))} file(s)."
        )
    finally:
        _safe_close_qdrant_client(client)


if __name__ == "__main__":
    main()
