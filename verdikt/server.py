"""FastAPI backend: streams an investigation to the browser over SSE.

The agent is synchronous (plain `requests` + the Anthropic SDK), so we run each
investigation on a worker thread and bridge its `emit` events into an async
Server-Sent-Events stream. The front end opens one EventSource, renders the plan
and lights up each source as its event arrives, then paints the brief.
"""
from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agent import Agent
from .config import CONFIG
from .renderer import brief_to_markdown
from .resolver import EntityResolver

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Verdikt", description="Evidence-to-Decision Engine")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "engine": "claude" if CONFIG.anthropic_api_key else "heuristic",
        "model": CONFIG.model,
        "keys": {
            "anthropic": bool(CONFIG.anthropic_api_key),
            "ncbi": bool(CONFIG.ncbi_api_key),
            "openfda": bool(CONFIG.openfda_api_key),
        },
    }


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@app.get("/api/resolve")
def resolve(q: str):
    """Human-in-the-loop step: what did the user mean? Returns the best match
    plus alternatives so the browser can let the user confirm before we invest."""
    entity = EntityResolver().resolve(q)
    return {"query": q, "entity": entity.as_dict() if entity else None}


@app.get("/api/investigate")
async def investigate(request: Request, q: str, id: str | None = None,
                      kind: str | None = None, name: str | None = None,
                      note: str | None = None, depth: str = "quick"):
    """Stream an investigation for query `q` as Server-Sent Events.

    If the user confirmed a specific entity (id + kind), we honour it instead of
    re-resolving — that is the human-in-the-loop override. `depth` is "quick"
    (fast, cheap default) or "deep" (full due diligence, opt-in).
    """
    forced = {"id": id, "kind": kind, "name": name, "note": note} if id and kind else None
    depth = "deep" if depth == "deep" else "quick"
    events: "queue.Queue[dict | None]" = queue.Queue()

    def emit(event: dict) -> None:
        events.put(event)

    def run() -> None:
        try:
            Agent().investigate(q, emit, forced_entity=forced, depth=depth)
        except Exception as exc:  # surface, don't hang the stream
            events.put({"type": "error", "message": str(exc)})
        finally:
            events.put(None)  # sentinel: stream complete

    threading.Thread(target=run, daemon=True).start()

    async def stream():
        import asyncio

        yield _sse({"type": "start", "query": q})
        while True:
            if await request.is_disconnected():
                break
            try:
                event = events.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue
            if event is None:
                yield _sse({"type": "done"})
                break
            yield _sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/export/markdown")
async def export_markdown(request: Request):
    brief = await request.json()
    md = brief_to_markdown(brief)
    name = (brief.get("entity", {}).get("name") or "brief").replace(" ", "_")
    return PlainTextResponse(
        md,
        headers={"Content-Disposition": f'attachment; filename="verdikt_{name}.md"'},
        media_type="text/markdown",
    )


# -- static front end ---------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
