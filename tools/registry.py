"""Universal tool registry. LLM discovers tools via schemas."""
from __future__ import annotations

from typing import Any, Callable, Optional
from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    permissions: list[str] = Field(default_factory=lambda: ["READ"])
    risk_level: str = "low"
    timeout: int = 30


class ToolResult(BaseModel):
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_class: Optional[str] = None


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, tuple[ToolSpec, Callable]] = {}

    def register(self, spec: ToolSpec, handler: Callable):
        self._tools[spec.name] = (spec, handler)

    def list_schemas(self) -> list[dict]:
        schemas = []
        for name, (spec, _) in self._tools.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.input_schema,
                },
            })
        return schemas

    def get(self, name: str) -> Optional[tuple[ToolSpec, Callable]]:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def execute(self, name: str, arguments: dict) -> ToolResult:
        entry = self._tools.get(name)
        if not entry:
            return ToolResult(success=False, error=f"Unknown tool: {name}", error_class="NOT_FOUND")
        spec, handler = entry
        try:
            result = handler(**(arguments or {}))
            return ToolResult(success=True, output=result)
        except TypeError as e:
            return ToolResult(success=False, error=f"Invalid arguments: {e}", error_class="INVALID_INPUT")
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e), error_class="NOT_FOUND")
        except Exception as e:
            err = str(e).lower()
            cls = "NETWORK" if any(x in err for x in ("timeout", "connection", "network", "dns")) else "TOOL_BUG"
            return ToolResult(success=False, error=str(e), error_class=cls)

    def describe(self) -> str:
        lines = []
        for name, (spec, _) in self._tools.items():
            lines.append(f"- {name}: {spec.description}")
        return "\n".join(lines) or "(no tools)"

    def call(self, name: str, arguments: dict) -> ToolResult:
        return self.execute(name, arguments)
