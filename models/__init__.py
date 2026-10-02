from .interface import Message, ModelProvider, ModelResponse, ToolCall

__all__ = [
    "Message",
    "ModelProvider",
    "ModelResponse",
    "ToolCall",
    "GroqProvider",
    "MockProvider",
]

def __getattr__(name):
    if name == "GroqProvider":
        from .groq_provider import GroqProvider
        return GroqProvider
    if name == "MockProvider":
        from .mock_provider import MockProvider
        return MockProvider
    if name == "DEFAULT_MODEL":
        from .groq_provider import DEFAULT_MODEL
        return DEFAULT_MODEL
    raise AttributeError(name)
