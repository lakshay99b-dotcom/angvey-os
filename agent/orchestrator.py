"""Central Agent Orchestrator — full task lifecycle."""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Optional

from models.interface import Message, ModelProvider, ModelResponse
from tools.registry import ToolRegistry, ToolResult
from memory.store import MemoryStore
from agent.state import TaskState, TaskStatus


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def prune_messages(messages: list[Message], max_chars: int = 24000) -> list[Message]:
    """Keep system + recent messages under approximate char budget."""
    if not messages:
        return messages
    system = [m for m in messages if m.role == "system"]
    rest = [m for m in messages if m.role != "system"]
    total = sum(len(m.content or "") for m in messages)
    if total <= max_chars:
        return messages
    # Keep last N that fit
    kept = []
    budget = max_chars - sum(len(m.content or "") for m in system) - 500
    for m in reversed(rest):
        c = len(m.content or "")
        if budget - c < 0 and kept:
            break
        kept.append(m)
        budget -= c
    kept.reverse()
    return system + kept


class Orchestrator:
    def __init__(
        self,
        model: ModelProvider,
        tools: ToolRegistry,
        memory: Optional[MemoryStore] = None,
        max_iterations: int = 8,
        on_event: Optional[Callable[[str, Any], None]] = None,
    ):
        self.model = model
        self.tools = tools
        self.memory = memory or MemoryStore()
        self.max_iterations = max_iterations
        self.on_event = on_event or (lambda k, d: None)

    def _emit(self, kind: str, detail: Any = None):
        self.on_event(kind, detail)

    def run(self, goal: str) -> TaskState:
        task = TaskState(goal=goal, model=getattr(self.model, "model", None) or getattr(self.model, "name", "unknown"))
        task.status = TaskStatus.PLANNING
        task.event("start", goal)
        task.save()
        self._emit("start", {"goal": goal, "task_id": task.task_id})

        system = self._build_system()
        messages: list[Message] = [
            Message(role="system", content=system),
            Message(role="user", content=f"Goal: {goal}\n\nPlan then execute using tools. When done, write a final answer and stop."),
        ]

        for it in range(self.max_iterations):
            task.status = TaskStatus.EXECUTING
            task.current_step = it
            messages = prune_messages(messages)
            self._emit("iteration", {"i": it, "msgs": len(messages)})

            try:
                resp: ModelResponse = self.model.chat(
                    messages,
                    tools=self.tools.list_schemas(),
                    max_tokens=800,
                )
            except Exception as e:
                err = f"model error: {e}"
                task.errors.append(err)
                task.event("error", err)
                self._emit("error", err)
                # backoff on rate limit
                if "429" in str(e) or "rate" in str(e).lower():
                    time.sleep(2 + it)
                    continue
                if it >= self.max_iterations - 1:
                    task.status = TaskStatus.FAILED
                    task.result = err
                    task.save()
                    return task
                continue

            task.tokens["prompt"] = task.tokens.get("prompt", 0) + (resp.usage or {}).get("prompt_tokens", 0)
            task.tokens["completion"] = task.tokens.get("completion", 0) + (resp.usage or {}).get("completion_tokens", 0)

            if resp.content:
                messages.append(Message(role="assistant", content=resp.content))
                task.event("thought", resp.content[:400])
                self._emit("thought", resp.content[:300])

            if resp.tool_calls:
                for tc in resp.tool_calls:
                    name = tc.name if hasattr(tc, "name") else tc.get("name")
                    args = tc.arguments if hasattr(tc, "arguments") else tc.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    self._emit("tool_call", {"name": name, "args": args})
                    result = self.tools.call(name, args)
                    obs = {
                        "tool": name,
                        "args": args,
                        "ok": result.ok,
                        "output": (result.output or "")[:3500],
                        "error": result.error,
                    }
                    task.tool_calls.append({"name": name, "args": args, "ok": result.ok})
                    task.observations.append(obs)
                    task.event("tool", obs)
                    self._emit("tool_result", obs)
                    tool_msg = f"Tool {name} -> ok={result.ok}\n{(result.output or result.error or '')[:3500]}"
                    messages.append(Message(role="user", content=tool_msg))
                    # nudge after write_file
                    if name == "write_file" and result.ok:
                        messages.append(Message(role="user", content="File written. If the goal is complete, provide the final answer now and stop calling tools."))
                task.save()
                continue

            # No tool calls — check if final
            if resp.content and any(k in (resp.content or "").lower() for k in ["final", "done", "completed", "summary", "report"]):
                task.status = TaskStatus.COMPLETED
                task.result = resp.content
                task.event("complete", resp.content[:500])
                task.save()
                self._emit("complete", task.result[:300] if task.result else None)
                return task

            if not resp.tool_calls and resp.content:
                # treat as final answer after a couple iterations
                if it >= 2:
                    task.status = TaskStatus.COMPLETED
                    task.result = resp.content
                    task.save()
                    self._emit("complete", task.result[:300] if task.result else None)
                    return task

        task.status = TaskStatus.FAILED if not task.result else TaskStatus.COMPLETED
        if not task.result:
            task.result = "Max iterations reached without clear completion."
        task.save()
        self._emit("done", {"status": task.status.value})
        return task

    def _build_system(self) -> str:
        tool_desc = self.tools.describe()
        return (
            "You are Angvey, a model-agnostic Agent OS. "
            "You plan, execute tools, observe results, and verify. "
            "Use tools when needed. Prefer web_search then fetch_url for research. "
            "Write important outputs with write_file. "
            "Keep responses concise. When the goal is satisfied, give a clear final answer.\n\n"
            f"Available tools:\n{tool_desc}"
        )
