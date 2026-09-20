import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from backend.services import auth_service, db_service
from gateway.contracts import ChatRequest, Contract, DocumentUpload, Identifier, MemoryWrite, Review
from gateway.errors import ControlError
from rag.models import Document
from rag.store import resource


class BodyLimit:
    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if sum(len(k) + len(v) for k, v in scope.get("headers", [])) > 16384:
            return await JSONResponse({"detail": "headers_size"}, 431)(scope, receive, send)
        count = 0
        messages = []
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    count += len(message.get("body", b""))
                    cap = self.maximum if scope.get("path", "").endswith("/pdf") or scope.get("path", "").startswith("/operations/") else 65536
                    if count > cap:
                        await JSONResponse({"detail": "request_size"}, 413)(scope, receive, send)
                        return
                    messages.append(message)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await JSONResponse({"detail": "request_timeout"}, 408)(scope, receive, send)
        async def replay():
            return messages.pop(0) if messages else await receive()
        async def headers(message):
            if message["type"] == "http.response.start":
                message["headers"].extend([(b"x-content-type-options", b"nosniff"),
                                           (b"cache-control", b"no-store"),
                                           (b"referrer-policy", b"no-referrer")])
            await send(message)
        await self.app(scope, replay, headers)


class ReleaseResponse(Response):
    def __init__(self, pipeline, prepared, stream):
        super().__init__()
        self.pipeline, self.prepared, self.stream = pipeline, prepared, stream

    async def __call__(self, scope, receive, send):
        lock = self.pipeline.store.locked()
        entered = False
        try:
            session, state = await run_in_threadpool(lock.__enter__)
            entered = True
            try:
                outcome = await run_in_threadpool(self.pipeline.release, self.prepared, session, state)
            except ControlError as exc:
                session.rollback()
                # The failed release emits only a static refusal; no stale answer survives.
                outcome = self.pipeline.denied(self.prepared.actor, self.prepared.request,
                                               self.prepared.outcome.request_id, exc).outcome
            if self.stream:
                body = "event: outcome\ndata: " + outcome.model_dump_json() + "\n\nevent: done\ndata: {}\n\n"
                response = Response(body, media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})
            else:
                response = JSONResponse(outcome.model_dump(mode="json"))
            # Bounded send while the DB release lock excludes completed revocation.
            async with asyncio.timeout(5):
                await response(scope, receive, send)
        except BaseException as exc:
            if entered:
                await run_in_threadpool(lock.__exit__, type(exc), exc, exc.__traceback__)
                entered = False
            # Do not expose exception text or attempt a second response after a partial send.
            if isinstance(exc, ControlError):
                await JSONResponse({"detail": exc.reason}, 503)(scope, receive, send)
            else:
                raise
        finally:
            if entered:
                await run_in_threadpool(lock.__exit__, None, None, None)


class Login(Contract):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class SourceBody(Contract):
    source_id: Identifier


def create_app(pipeline, ingestion, memories, parser=None):
    app = FastAPI(title="RagSec protected lab", version="0.1.0")
    app.state.pipeline = pipeline
    app.add_middleware(BodyLimit, maximum=pipeline.limits.upload_bytes + 65536)
    app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("RAGSEC_CORS_ORIGINS",
                       "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:3001").split(","),
                       allow_credentials=True, allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"])

    @app.exception_handler(ControlError)
    async def controlled_error(_request, exc):
        return JSONResponse({"detail": exc.reason}, status_code=503 if exc.status == "unavailable" else 403)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _exc):
        return JSONResponse({"detail": "invalid_request_schema"}, 422)

    def actor(current=Depends(auth_service.get_current_user)):
        membership = pipeline.store.actor(current["id"])
        if current.get("session_version") != membership.session_version:
            raise HTTPException(401, "session_revoked")
        return membership

    @app.get("/healthz")
    def health():
        return {"status": "alive", "mode": "protected", "provider": pipeline.provider.model}

    @app.get("/readyz")
    def ready():
        if not pipeline.policy.ready():
            return JSONResponse({"status": "unavailable", "reason": "policy_unavailable"}, 503)
        try:
            with pipeline.store.locked():
                pass
            pipeline.retrieval.reader.client.get_collections()
        except Exception:
            return JSONResponse({"status": "unavailable", "reason": "data_unavailable"}, 503)
        return {"status": "ready", "policy": "ragsec-1"}

    @app.post("/api/v1/auth/login")
    def login(body: Login):
        failed = False
        with pipeline.store.locked() as (session, _state):
            user = session.scalar(select(db_service.User).where(db_service.User.email == body.email))
            if not user:
                raise HTTPException(401, "invalid_credentials")
            now = datetime.now(timezone.utc)
            locked = user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now
            if locked or not db_service.verify_password(user.password, body.password):
                failed = True
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
                if user.failed_login_attempts >= 5:
                    user.locked_until = now + timedelta(minutes=5)
            else:
                user.failed_login_attempts, user.locked_until = 0, None
                member = pipeline.store.actor(user.id, session)
                result = {"access_token": auth_service.create_access_token(user.id, user.email, user.role, member.session_version),
                    "token_type": "bearer", "user": {"id": user.id, "email": user.email, "role": user.role,
                                                       "class_label": None, "language": user.language},
                    "tenant": member.tenant}
        if failed:
            raise HTTPException(401, "invalid_credentials")
        return result

    @app.get("/api/v1/auth/me")
    def me(current=Depends(actor)):
        with pipeline.store.sessions() as session:
            user = session.get(db_service.User, current.id)
            return {"id": user.id, "email": user.email, "role": user.role,
                    "class_label": None, "language": user.language}

    @app.post("/api/v1/auth/logout")
    def logout(current=Depends(actor)):
        from rag.models import Membership
        with pipeline.store.locked() as (session, _state):
            pipeline.store.current(current, session)
            session.get(Membership, current.id).session_version += 1
        return {"success": True}

    async def prepare_connected(request, body, current):
        work = asyncio.create_task(pipeline.prepare(current, body))
        async def disconnect():
            while True:
                if (await request.receive())["type"] == "http.disconnect":
                    return
        watcher = asyncio.create_task(disconnect())
        try:
            done, _ = await asyncio.wait({work, watcher}, return_when=asyncio.FIRST_COMPLETED)
            if work in done:
                return await work
            work.cancel()
            raise asyncio.CancelledError()
        finally:
            watcher.cancel()
            if not work.done():
                work.cancel()
            await asyncio.gather(watcher, work, return_exceptions=True)

    @app.post("/api/v1/chat")
    async def chat(request: Request, body: ChatRequest, current=Depends(actor)):
        return ReleaseResponse(pipeline, await prepare_connected(request, body, current), False)

    @app.post("/api/v1/chat/stream")
    async def stream(request: Request, body: ChatRequest, current=Depends(actor)):
        return ReleaseResponse(pipeline, await prepare_connected(request, body, current), True)

    @app.get("/api/v1/citations/verify")
    def citation(token: str, answer_hash: str | None = None, current=Depends(actor)):
        return pipeline.citations.verify(token, current, pipeline.store, pipeline.policy, answer_hash)

    @app.post("/api/v1/admin/sources")
    def source(body: SourceBody, current=Depends(actor)):
        ingestion.register_source(current, body.source_id)
        return {"status": "registered"}

    @app.post("/api/v1/admin/documents")
    def upload(body: DocumentUpload, current=Depends(actor)):
        return {"document_id": ingestion.stage(current, body)}

    @app.post("/api/v1/admin/documents/pdf")
    async def pdf(request: Request, source_id: Identifier, classification: str = "public", current=Depends(actor)):
        if parser is None:
            raise ControlError("parser_unavailable", "unavailable")
        # Authorize before handing bytes to an isolated parser.
        from gateway.contracts import Resource
        pipeline.policy.require(current, "ingest", Resource(id=source_id, tenant=current.tenant, owner=current.id,
                                classification=classification, status="staged", version=1, access_version=1))
        raw = await request.body()
        extracted = await run_in_threadpool(parser.extract, raw)
        body = DocumentUpload(source_id=source_id, classification=classification, text=extracted)
        return {"document_id": await run_in_threadpool(ingestion.stage, current, body,
                                                        original=raw, parser_version="pdfplumber-0.11.9")}

    @app.get("/api/v1/admin/documents")
    def documents(current=Depends(actor)):
        from gateway.contracts import Resource
        pipeline.policy.require(current, "manage", Resource(id="corpus", tenant=current.tenant, owner=current.id,
                                classification="public", status="indexed", version=1, access_version=1))
        with pipeline.store.sessions() as session:
            docs = session.scalars(select(Document).where(Document.tenant == current.tenant)).all()
            return [{"id": d.id, "status": d.status, "version": d.version, "classification": d.classification,
                     "signals": json.loads(d.signals_json), "source_id": d.source_id} for d in docs]

    @app.post("/api/v1/admin/documents/{doc_id}/review")
    def review(doc_id: Identifier, body: Review, current=Depends(actor)):
        ingestion.review(current, doc_id, body.version, body.approve)
        return {"status": "approved" if body.approve else "quarantined"}

    @app.post("/api/v1/admin/publish")
    def publish(current=Depends(actor)):
        ingestion.publish(current)
        return {"status": "published"}

    @app.delete("/api/v1/admin/documents/{doc_id}")
    def revoke(doc_id: Identifier, current=Depends(actor)):
        ingestion.revoke(current, doc_id)
        pipeline.cache.invalidate(doc_id)
        return {"status": "revoked", "cleanup": "queued"}

    @app.get("/api/v1/documents/{doc_id}")
    def download(doc_id: Identifier, current=Depends(actor)):
        with pipeline.store.locked() as (session, _state):
            pipeline.store.current(current, session)
            doc = pipeline.store.document(doc_id, session)
            pipeline.policy.require(current, "download", resource(doc))
            return Response(doc.text, media_type="text/plain", headers={"Content-Disposition": "attachment; filename=source.txt"})

    @app.post("/api/v1/memory")
    def remember(body: MemoryWrite, current=Depends(actor)):
        return {"id": memories.write(current, body)}

    @app.get("/api/v1/memory/{memory_id}")
    def recall(memory_id: Identifier, current=Depends(actor)):
        return {"text": memories.operation(current, memory_id)}

    @app.delete("/api/v1/memory/{memory_id}")
    def forget(memory_id: Identifier, current=Depends(actor)):
        memories.operation(current, memory_id, "memory_delete")
        return {"status": "deleted"}

    return app
