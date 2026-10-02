from .registry import ToolRegistry, ToolSpec, ToolResult
from .web import register_web_tools
from .files import register_file_tools

def build_default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_web_tools(reg)
    register_file_tools(reg)
    return reg
