"""Tanya Dino API. The dashboard talks to this and nothing else.

    cp agent/.env.example agent/.env      # then put your Gemini key in it
    uvicorn agent.server:app --port 7860  # run from the repo root

Endpoints
    GET  /health   is it up, which model, does the coverage model exist yet
    POST /ask      { "question": "..." } -> the contract the dashboard expects

The dashboard degrades on its own if this is down, so nothing here needs to
guarantee uptime. It does need to never invent a number: every figure in a
response comes from agent/tools.py, and `map.ids` is taken from tool output
rather than from anything the model wrote.
"""
from __future__ import annotations

import json
import os
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import tools as T

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

app = FastAPI(title="Tanya Dino")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["*"], allow_headers=["*"],
)


class CmpContext(BaseModel):
    """The District Decision Comparison the user is looking at.

    Names and a level, never numbers. The figures are recomputed from the
    dataset in graph.seed_comparison(), so a client cannot hand the model a
    made-up figure and have the number guardrail treat it as data.
    """
    level: str = Field(default="district", max_length=16)
    areas: list[str] = Field(default_factory=list, max_length=25)
    # Or the deployment portfolio, sent the same way: the SETTINGS, never the
    # figures, so the graph recomputes what the panel drew.
    budget_rm: float | None = Field(default=None, ge=0, le=1e12)
    scenario: str = Field(default="", max_length=16)


class Ask(BaseModel):
    # Bounded so a pasted essay cannot be forwarded to the model as-is.
    question: str = Field(min_length=1, max_length=2000)
    # One LangGraph thread per chat panel, so follow-up questions resolve "it".
    session_id: str | None = Field(default=None, max_length=64)
    context: CmpContext | None = None


@app.get("/health")
def health():
    return {
        "ok": True,
        "settlements": len(T.DF),
        "coverage_model_columns": T.HAS_MODEL,
        "gemini_key_present": bool(os.getenv("GOOGLE_API_KEY", "").strip()),
        "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        "tools": sorted(T.TOOLS),
    }


def _ctx(body: "Ask") -> dict | None:
    return body.context.model_dump() if body.context else None


def _error_payload(e: Exception) -> dict:
    return {
        "answer": f"The copilot could not complete that: {e}. {T.DISCLAIMER}",
        "table": [], "map": {"action": "highlight", "ids": []},
        "response_type": "error", "tools_used": [], "error": str(e),
    }


@app.post("/ask")
def ask(body: Ask):
    from .graph import ask as run_graph
    try:
        return run_graph(body.question, body.session_id, _ctx(body))
    except Exception as e:
        # A failure here is answered honestly rather than silently faked. The
        # dashboard renders it as a normal bubble.
        traceback.print_exc()
        return _error_payload(e)


@app.post("/ask/stream")
def ask_stream(body: Ask):
    """Server-sent events: one `step` per graph node transition, then `done`.

    The steps are the graph's real node updates, not a scripted animation. A
    client that cannot stream still has POST /ask, and the dashboard falls back
    to it automatically.
    """
    from .graph import ask_stream as run_stream

    def gen():
        try:
            for event, data in run_stream(body.question, body.session_id, _ctx(body)):
                yield f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
        except Exception as e:                    # never leave the stream hanging
            traceback.print_exc()
            yield f"event: done\ndata: {json.dumps(_error_payload(e))}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
