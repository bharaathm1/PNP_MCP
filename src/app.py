"""
MCP Application Instance.

This module holds the global FastMCP instance to avoid circular imports
between the server entry point and the tools/resources modules.
"""

from fastmcp import FastMCP
from config.settings import settings

# Global MCP instance
mcp = FastMCP(name=settings.SERVER_NAME)
