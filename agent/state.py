"""Persistent task state."""
from __future__ import annotations

import json
import os
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

def _tasks_dir() -> Path:
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        d = Path("/tmp/angvey/tasks")
    else:
        d = Path(__file__).resolve().parent.parent / "data" / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    return d

TASKS_DIR = _tasks_dir()


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskEvent(BaseModel):
    ts: float = Field(default_factory=time.time)
    kind: str
    detail: Any = None


class TaskState(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    plan: list[str] = Field(default_factory=list)
    current_step: int = 0
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    retries: int = 0
    result: Optional[str] = None
    model: Optional[str] = None
    tokens: dict[str, int] = Field(default_factory=dict)
    events: list[TaskEvent] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def event(self, kind: str, detail: Any = None):
        self.events.append(TaskEvent(kind=kind, detail=detail))
        self.updated_at = time.time()

    def save(self):
        path = TASKS_DIR / f"{self.task_id}.json"
        path.write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, task_id: str) -> "TaskState":
        path = TASKS_DIR / f"{task_id}.json"
        return cls.model_validate_json(path.read_text())
