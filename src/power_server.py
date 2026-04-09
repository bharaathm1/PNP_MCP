"""
Power Analysis MCP Server - Standalone FastMCP server for power measurement data.

This server exposes two MCP tools:
  find_power_summary_files  — Discover *_summary.csv files in a folder tree.
  compile_power_data        — Run the full pipeline and return the complete markdown.

It also registers a system prompt (power_analysis_prompt) that teaches the
connected LLM the full analysis workflow, tool inputs/outputs, and decision tree.

Default port: 8002  (override via POWER_SERVER_PORT env var)
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
from tools import power_tools          # noqa: F401  registers all 9 power tools
from tools import power_rail_knowledge_tools  # noqa: F401  registers load/get/search power rail knowledge

# ---------------------------------------------------------------------------
# Register prompt
# ---------------------------------------------------------------------------
from prompts import power_prompt       # noqa: F401  registers power_analysis_prompt


# ---------------------------------------------------------------------------
# Auth helpers (identical pattern to etl_server.py)
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
    """Return (mcp_instance, auth_token|None). Mirrors etl_server.py logic."""
    auth_token = None

    if secure:
        auth_token = get_or_generate_token(settings.SECRET_KEY)
        verifier = StaticTokenVerifier(
            tokens={
                auth_token: {
                    "client_id": "mcp-power-client",
                    "scopes": ["read:data", "write:data", "execute:tools"],
                }
            },
            required_scopes=["read:data"],
        )
        app.mcp = FastMCP(name="Power Analysis Server", auth=verifier)

        import importlib
        importlib.reload(power_tools)
        importlib.reload(power_prompt)

    return app.mcp, auth_token


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Power Analysis MCP Server")
    parser.add_argument("--secure", action="store_true", help="Enable JWT token authentication")
    parser.add_argument("--sse", action="store_true", help="Use SSE transport (default: Streamable HTTP)")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("POWER_SERVER_PORT", "8002")),
        help="Port to listen on (default: 8002 or POWER_SERVER_PORT env var)",
    )
    args = parser.parse_args()

    mcp_instance, auth_token = initialize_mcp_with_auth(secure=args.secure)
    transport = "sse" if args.sse else "http"
    host = settings.HOST
    port = args.port

    print("Starting Power Analysis MCP Server...")
    print(f"Environment : {settings.ENVIRONMENT}")
    print(f"Transport   : {'SSE' if args.sse else 'HTTP (Streamable)'}")
    print(f"Host        : {host}:{port}")
    print(f"MCP Endpoint: http://{host}:{port}/mcp")
    print(f"Auth        : {'ENABLED' if args.secure else 'DISABLED'}")
    print("Tools       : find_power_summary_files, compile_power_data")
    print("Prompts     : power_analysis_prompt")

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
