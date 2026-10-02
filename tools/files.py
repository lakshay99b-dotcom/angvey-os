"""File tools — sandboxed workspace under data/files."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .registry import ToolRegistry, ToolSpec

def _files_root() -> Path:
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        root = Path("/tmp/angvey/files")
    else:
        root = Path(__file__).resolve().parent.parent / "data" / "files"
    root.mkdir(parents=True, exist_ok=True)
    return root

FILES_ROOT = _files_root()


def write_file(filename: str, content: str) -> dict[str, Any]:
    safe = Path(filename).name
    if not safe or safe in (".", ".."):
        raise ValueError("Invalid filename")
    if ".." in filename or filename.startswith("/"):
        raise ValueError("Path traversal not allowed")
    path = FILES_ROOT / safe
    path.write_text(content, encoding="utf-8")
    return {
        "path": str(path),
        "filename": safe,
        "bytes": len(content.encode("utf-8")),
        "exists": path.exists(),
    }


def read_file(filename: str) -> dict[str, Any]:
    safe = Path(filename).name
    path = FILES_ROOT / safe
    if not path.exists():
        raise FileNotFoundError(f"File not found: {safe}")
    content = path.read_text(encoding="utf-8")
    return {"filename": safe, "content": content, "bytes": len(content.encode("utf-8"))}


def list_files() -> list[str]:
    return sorted([p.name for p in FILES_ROOT.iterdir() if p.is_file()])


def register_file_tools(registry: ToolRegistry):
    registry.register(
        ToolSpec(
            name="write_file",
            description="Write content to a file in the Angvey workspace (e.g. a research report in Markdown).",
            input_schema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Filename only, e.g. report.md"},
                    "content": {"type": "string", "description": "Full file content"},
                },
                "required": ["filename", "content"],
            },
            permissions=["WRITE"],
            risk_level="medium",
        ),
        write_file,
    )
    registry.register(
        ToolSpec(
            name="read_file",
            description="Read a file from the Angvey workspace.",
            input_schema={
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"],
            },
            permissions=["READ"],
            risk_level="low",
        ),
        read_file,
    )
    registry.register(
        ToolSpec(
            name="list_files",
            description="List files currently in the Angvey workspace.",
            input_schema={"type": "object", "properties": {}},
            permissions=["READ"],
            risk_level="low",
        ),
        list_files,
    )
