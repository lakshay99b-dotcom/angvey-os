"""Model-agnostic provider interface."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel, Field

class Message(BaseModel):
    role: str
    content: Optional[str] = None
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

class ModelResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    raw: Any = None
    usage: dict[str, int] = Field(default_factory=dict)
    finish_reason: Optional[str] = None

class ModelProvider(ABC):
    @abstractmethod
    def generate(self, messages: list[Message], tools: Optional[list[dict]] = None, temperature: float = 0.2, max_tokens: int = 800) -> ModelResponse:
        ...
    @property
    @abstractmethod
    def name(self) -> str:
        ...
