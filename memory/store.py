"""Lightweight persistent memory: task learnings + simple key-value."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

def _mem_dir() -> Path:
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        d = Path("/tmp/angvey/memory")
    else:
        d = Path(__file__).resolve().parent.parent / "data" / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d

MEM_DIR = _mem_dir()
LEARNINGS = MEM_DIR / "learnings.jsonl"
PREFS = MEM_DIR / "preferences.json"


class MemoryStore:
    def store_learning(self, task_goal: str, learning: str, meta: Optional[dict] = None):
        entry = {"ts": time.time(), "goal": task_goal, "learning": learning, "meta": meta or {}}
        with open(LEARNINGS, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def retrieve_learnings(self, query: str = "", limit: int = 5) -> list[dict]:
        if not LEARNINGS.exists():
            return []
        rows = []
        with open(LEARNINGS, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if query:
            q = query.lower()
            rows = [r for r in rows if q in (r.get("goal") or "").lower() or q in (r.get("learning") or "").lower()]
        return rows[-limit:]

    def set_pref(self, key: str, value: Any):
        prefs = {}
        if PREFS.exists():
            prefs = json.loads(PREFS.read_text())
        prefs[key] = value
        PREFS.write_text(json.dumps(prefs, indent=2))

    def get_pref(self, key: str, default: Any = None) -> Any:
        if not PREFS.exists():
            return default
        prefs = json.loads(PREFS.read_text())
        return prefs.get(key, default)
