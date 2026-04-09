"""
SocWatch MCP Server - Standalone FastMCP server for Intel SocWatch CSV analysis.

This server exposes three MCP tools:
  find_socwatch_files  — Discover SocWatch CSV files in a folder tree.
  parse_socwatch_data  — Parse them into Excel + Markdown summary; returns compact metadata only.
  query_socwatch_data  — Return specific sections from the compiled Markdown (< 2 KB per query).

It also registers a system prompt (socwatch_analysis_prompt) that teaches the
connected LLM the three-phase workflow, tool inputs/outputs, and common mistakes.

Default port: 8000  (override via SOCWATCH_SERVER_PORT env var)
"""

import sys
import argparse
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — file lives in src/, project root is one level up
# ---------------------------------------------------------------------------
src_dir = Path(__file__).parent          # src/
project_root = Path(__file__).parent.parent  # fastmcp-server-template/
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from config.settings import settings
import app

# ---------------------------------------------------------------------------
# Register tools
# ---------------------------------------------------------------------------
from tools import socwatch_tools          # registers find_socwatch_files + parse_socwatch_data
from tools import power_rail_knowledge_tools  # registers load/get/search power rail knowledge

# ---------------------------------------------------------------------------
# Register prompt
# ---------------------------------------------------------------------------
from prompts import socwatch_prompt       # registers socwatch_analysis_prompt


# ---------------------------------------------------------------------------
# Auth helpers (identical to server.py)
# ---------------------------------------------------------------------------

def get_or_generate_token(secret_key: str) -> str:
    # Shared token file — same token used by all servers
    token_file = project_root / ".mcp-token"
    if token_file.exists():
        token = token_file.read_text().strip()
        if token:
            return token
    return _generate_token(secret_key)


def _generate_token(secret_key: str) -> str:
    import hashlib
    token_hash = hashlib.sha256(secret_key.encode()).hexdigest()
    return f"mcp-token-{token_hash[:32]}"


def initialize_mcp_with_auth(secure: bool = False):
    """Return (mcp_instance, auth_token|None). Mirrors server.py logic."""
    auth_token = None

    if secure:
        auth_token = get_or_generate_token(settings.SECRET_KEY)
        verifier = StaticTokenVerifier(
            tokens={
                auth_token: {
                    "client_id": "mcp-socwatch-client",
                    "scopes": ["read:data", "write:data", "execute:tools"],
                }
            },
            required_scopes=["read:data"],
        )
        app.mcp = FastMCP(name="SocWatch Analysis Server", auth=verifier)

        import importlib
        importlib.reload(socwatch_tools)
        importlib.reload(socwatch_prompt)

    return app.mcp, auth_token


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SocWatch MCP Server")
    parser.add_argument("--secure", action="store_true", help="Enable JWT token authentication")
    parser.add_argument("--sse", action="store_true", help="Use SSE transport (default: Streamable HTTP)")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SOCWATCH_SERVER_PORT", "8000")),
        help="Port to listen on (default: 8000 or SOCWATCH_SERVER_PORT env var)",
    )
    args = parser.parse_args()

    mcp_instance, auth_token = initialize_mcp_with_auth(secure=args.secure)
    transport = "sse" if args.sse else "http"
    host = settings.HOST
    port = args.port

    print(f"Starting SocWatch Analysis Server...")
    print(f"Environment : {settings.ENVIRONMENT}")
    print(f"Transport   : {'SSE' if args.sse else 'HTTP (Streamable)'}")
    print(f"Host        : {host}:{port}")
    print(f"MCP Endpoint: http://{host}:{port}/mcp")
    print(f"Auth        : {'ENABLED' if args.secure else 'DISABLED'}")
    print(f"Tools       : find_socwatch_files, parse_socwatch_data")
    print(f"Prompts     : socwatch_analysis_prompt")

    if args.secure and auth_token:
        token_file = project_root / ".mcp-token"
        if not token_file.exists():
            old_umask = os.umask(0o177)
            try:
                token_file.write_text(auth_token)
                os.chmod(token_file, 0o600)
            finally:
                os.umask(old_umask)
            print(f"\nToken saved to: {token_file}")
        else:
            print(f"\nToken loaded from: {token_file}")
        print(f"Authorization: Bearer {auth_token}\n")

    mcp_instance.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    main()
