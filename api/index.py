"""Vercel serverless entry for Angvey Agent OS."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Angvey Agent OS", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    goal: str
    mock: bool = False
    model: Optional[str] = None
    max_iters: int = 6


@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok", "service": "angvey-agent-os", "version": "0.1.0"}


@app.get("/api/tools")
def list_tools():
    from tools import build_default_registry
    reg = build_default_registry()
    return {"tools": [{"name": n} for n in reg.names()], "schemas": reg.list_schemas()}


@app.post("/api/agent/run")
def run_agent(req: RunRequest):
    from tools import build_default_registry
    from memory.store import MemoryStore
    from agent.orchestrator import Orchestrator

    if req.mock:
        from models.mock_provider import MockProvider
        model = MockProvider()
    else:
        from models.groq_provider import GroqProvider, DEFAULT_MODEL
        model = GroqProvider(model=req.model or DEFAULT_MODEL)

    events = []
    def on_event(k, d):
        events.append({"kind": k, "detail": str(d)[:500] if not isinstance(d, (dict, list)) else d})

    orch = Orchestrator(
        model=model,
        tools=build_default_registry(),
        memory=MemoryStore(),
        max_iterations=min(req.max_iters, 8),
        on_event=on_event,
    )
    task = orch.run(req.goal)
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "result": task.result,
        "tool_calls": task.tool_calls,
        "tokens": task.tokens,
        "errors": task.errors[:5],
        "model": task.model,
        "events": events[-20:],
    }
