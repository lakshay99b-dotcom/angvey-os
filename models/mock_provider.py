"""Mock provider for offline tests — no API key required."""
from __future__ import annotations

import json
from typing import Any, Optional

from .interface import Message, ModelProvider, ModelResponse, ToolCall


class MockProvider(ModelProvider):
    def __init__(self, model: str = "mock"):
        self.model = model
        self._step = 0

    @property
    def name(self) -> str:
        return f"mock/{self.model}"

    def generate(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> ModelResponse:
        self._step += 1
        goal = ""
        for m in messages:
            if m.role == "user" and m.content and "Goal:" in (m.content or ""):
                goal = m.content
                break
        if self._step == 1 and tools:
            return ModelResponse(
                content="I will search for information related to the goal.",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="web_search",
                        arguments={"query": "AI agent architecture", "max_results": 3},
                    )
                ],
                usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            )
        if self._step == 2:
            return ModelResponse(
                content="Based on the search results, here is a concise summary of AI agent architectures. Final answer complete.",
                tool_calls=[],
                usage={"prompt_tokens": 200, "completion_tokens": 40, "total_tokens": 240},
            )
        return ModelResponse(
            content="Task completed (mock).",
            tool_calls=[],
            usage={"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
        )
