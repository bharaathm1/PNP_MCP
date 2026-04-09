"""
MCP Tool Decorators - Utility decorators for MCP tools.

This module provides decorators that can be applied to MCP tools to modify
their behavior or add metadata to their responses, particularly for signaling
when responses should be embedded rather than sent directly to the LLM.
"""

from functools import wraps
from typing import Any, Callable, TypeVar
import json

try:
    from fastmcp.tools.tool import ToolResult
except ImportError:
    # Fallback if running outside of FastMCP context
    class ToolResult:  # type: ignore
        def __init__(self, content=None, structured_content=None, meta=None):
            self.content = content
            self.structured_content = structured_content
            self.meta = meta or {}

F = TypeVar('F', bound=Callable[..., Any])


def embed_response(func: F) -> F:
    """
    Pass-through decorator (ToolResult.meta not supported in installed fastmcp).
    Kept for API compatibility — simply calls and returns the original function result.
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)
    wrapper._has_embed_decorator = True  # type: ignore
    return wrapper  # type: ignore
    return wrapper  # type: ignore


def embed_if_large(threshold: int = 5000) -> Callable[[F], F]:
    """
    Decorator that was intended to mark large responses for embedding via ToolResult.meta,
    but the installed fastmcp version does not support the 'meta' kwarg on ToolResult.
    Currently acts as a transparent pass-through — the tool function is called and its
    result returned unchanged. The threshold parameter is accepted for API compatibility.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        wrapper._has_embed_decorator = True  # type: ignore
        wrapper._embed_threshold = threshold  # type: ignore
        return wrapper  # type: ignore

    return decorator


def embed_with_metadata(content_type: str = "document", **metadata: Any) -> Callable[[F], F]:
    """
    Pass-through decorator (ToolResult.meta not supported in installed fastmcp).
    Kept for API compatibility — simply calls and returns the original function result.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        wrapper._has_embed_decorator = True  # type: ignore
        wrapper._embed_content_type = content_type  # type: ignore
        return wrapper  # type: ignore
    return decorator


def metadata(**meta_fields: Any) -> Callable[[F], F]:
    """
    Pass-through decorator (ToolResult.meta not supported in installed fastmcp).
    Kept for API compatibility — simply calls and returns the original function result.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
        wrapper._has_metadata_decorator = True  # type: ignore
        return wrapper  # type: ignore
    return decorator


def async_tool(fn: F) -> F:
    """
    Wrap a synchronous MCP tool function to run in anyio's thread pool, freeing
    the asyncio event loop for other requests while blocking I/O executes.

    Usage:
        @mcp.tool()
        @async_tool
        @embed_if_large(threshold=7000)
        def my_tool(arg: str) -> dict:
            ...  # blocking I/O safe here
    """
    import anyio
    from functools import partial as _partial

    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return await anyio.to_thread.run_sync(_partial(fn, *args, **kwargs))

    return wrapper  # type: ignore
