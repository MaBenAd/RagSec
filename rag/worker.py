import asyncio
import base64
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient
from starlette.concurrency import run_in_threadpool
from pydantic import Field

from backend.services.db_service import engine
from gateway.app import BodyLimit
from gateway.contracts import Contract, DocumentUpload, Identifier
from gateway.errors import ControlError
from gateway.policy import Policy
from rag.ingestion import Ingestion
from rag.store import Store
from rag.vectors import VectorWriter


class Operation(Contract):
    actor_id: int = Field(gt=0)
    source_id: Identifier | None = None
    doc_id: Identifier | None = None
    upload: DocumentUpload | None = None
    original: str | None = Field(default=None, max_length=2800000)
    parser_version: str = "plain-text-v1"
    version: int = 1
    approve: bool = False


def application():
    token = os.environ["RAGSEC_INGEST_TOKEN"]
    if len(token) < 32:
        raise RuntimeError("Weak ingestion token")
    store = Store(engine)
    policy = Policy(os.environ.get("RAGSEC_OPA_URL", "http://opa:8181"), token=os.environ.get("RAGSEC_OPA_TOKEN"))
    vectors = QdrantClient(url=os.environ.get("QDRANT_URL", "http://qdrant:6333"),
                           api_key=os.environ["QDRANT_WRITE_KEY"], timeout=10, check_compatibility=False)
    ingestion = Ingestion(store, policy, VectorWriter(vectors), staging_root="/staging")

    async def maintenance():
        while True:
            try:
                await run_in_threadpool(ingestion.cleanup)
                findings = await run_in_threadpool(ingestion.integrity)
                if findings:
                    # IDs and stable reason codes only; never document text or exception text.
                    import logging
                    logging.getLogger("ragsec.integrity").warning("index_mismatch count=%d", len(findings))
            except Exception:
                import logging
                logging.getLogger("ragsec.worker").warning("maintenance_unavailable")
            await asyncio.sleep(60)

    @asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(maintenance())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        vectors.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(BodyLimit, maximum=3 * 1024**2)

    def authenticated(authorization: str = Header(default="")):
        if not secrets.compare_digest(authorization, f"Bearer {token}"):
            raise ControlError("service_denied")

    @app.exception_handler(ControlError)
    async def controlled(_request, exc):
        return JSONResponse({"detail": exc.reason}, 403)

    @app.post("/operations/{action}", dependencies=[Depends(authenticated)])
    def operation(action: str, body: Operation):
        actor = store.actor(body.actor_id)
        if action == "source" and body.source_id:
            result = ingestion.register_source(actor, body.source_id)
        elif action == "stage" and body.upload:
            original = base64.b64decode(body.original, validate=True) if body.original else None
            result = ingestion.stage(actor, body.upload, original=original, parser_version=body.parser_version)
        elif action == "review" and body.doc_id:
            result = ingestion.review(actor, body.doc_id, body.version, body.approve)
        elif action == "publish":
            result = ingestion.publish(actor)
        elif action == "revoke" and body.doc_id:
            result = ingestion.revoke(actor, body.doc_id)
        else:
            raise ControlError("operation_unknown")
        return {"result": result}

    return app
