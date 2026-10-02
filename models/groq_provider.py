"""Groq ModelProvider implementation."""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Optional

from groq import Groq

from .interface import Message, ModelProvider, ModelResponse, ToolCall

DEFAULT_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODELS = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "mixtral-8x7b-32768"]


class GroqProvider(ModelProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
            if os.path.isfile(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("GROQ_API_KEY="):
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
        if not key:
            raise ValueError("GROQ_API_KEY required")
        self.client = Groq(api_key=key)
        self.model = model

    @property
    def name(self) -> str:
        return f"groq/{self.model}"

    def generate(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> ModelResponse:
        groq_messages: list[dict[str, Any]] = []
        for m in messages:
            msg: dict[str, Any] = {"role": m.role}
            if m.content is not None:
                msg["content"] = m.content
            else:
                msg["content"] = m.content or ""
            if m.name:
                msg["name"] = m.name
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            groq_messages.append(msg)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": groq_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            completion = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            err = str(e).lower()
            if "model" in err and ("not found" in err or "does not exist" in err):
                last = e
                for fb in FALLBACK_MODELS:
                    if fb == self.model:
                        continue
                    try:
                        kwargs["model"] = fb
                        completion = self.client.chat.completions.create(**kwargs)
                        self.model = fb
                        last = None
                        break
                    except Exception as e2:
                        last = e2
                if last is not None:
                    raise last
            else:
                raise

        choice = completion.choices[0]
        message = choice.message
        tool_calls: list[ToolCall] = []
        if getattr(message, "tool_calls", None):
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": tc.function.arguments}
                tool_calls.append(
                    ToolCall(
                        id=tc.id or str(uuid.uuid4()),
                        name=tc.function.name,
                        arguments=args if isinstance(args, dict) else {"value": args},
                    )
                )
        usage: dict[str, int] = {}
        if completion.usage:
            usage = {
                "prompt_tokens": completion.usage.prompt_tokens or 0,
                "completion_tokens": completion.usage.completion_tokens or 0,
                "total_tokens": completion.usage.total_tokens or 0,
            }
        return ModelResponse(
            content=message.content,
            tool_calls=tool_calls,
            raw=completion,
            usage=usage,
            finish_reason=getattr(choice, "finish_reason", None),
        )
