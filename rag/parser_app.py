import asyncio
import json
import os
from pathlib import Path
import sys
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
slots = asyncio.Semaphore(2)


@app.post("/parse")
async def parse(request: Request):
    async with slots:
        raw = bytearray()
        async for part in request.stream():
            raw.extend(part)
            if len(raw) > 2 * 1024**2:
                return JSONResponse({"detail": "pdf_size"}, 413)
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-I", str(Path(__file__).with_name("pdf_worker.py")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env={"PATH": "/usr/local/bin:/usr/bin", "LANG": "C.UTF-8"})
        try:
            output, _ = await asyncio.wait_for(process.communicate(bytes(raw)), timeout=10)
            if process.returncode or len(output) > 132096:
                return JSONResponse({"detail": "pdf_invalid"}, 422)
            return json.loads(output)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            return JSONResponse({"detail": "pdf_timeout"}, 422)
