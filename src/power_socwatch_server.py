"""
Power + SocWatch Combined MCP Server
=====================================
Unified FastMCP server that exposes both power rail measurement tools and
Intel SocWatch hardware telemetry tools in a single server instance.

Tools registered:
  Power (3):
    find_power_summary_files  — Discover *_summary.csv files; check if compiled.
    compile_power_data        — Run full 3-step pipeline; writes Excel/CSV/Markdown.
    query_power_matrix        — Filter + average the compiled matrix (<2 KB per call).

  SocWatch (3):
    find_socwatch_files       — Discover SocWatch CSV files in a folder tree.
    parse_socwatch_data       — Parse CSVs into Excel + Markdown; returns metadata only.
    query_socwatch_data       — Read specific sections from compiled Markdown.

  Knowledge (2):
    load_power_rail_knowledge_to_mongodb  — Seed KB once at session start.
    search_power_rail_knowledge           — Look up rail descriptions, debug hints, SocWatch metrics.

Prompts:
    power_socwatch_analysis_prompt  — Unified 3-phase workflow system prompt.

Default port: 8000  (override via POWER_SOCWATCH_SERVER_PORT env var)

Usage:
    python src/power_socwatch_server.py
    python src/power_socwatch_server.py --port 8003
    python src/power_socwatch_server.py --secure
    python src/power_socwatch_server.py --sse
"""

import sys
import argparse
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — file lives in src/, project root is one level up
# ---------------------------------------------------------------------------
src_dir = Path(__file__).parent              # src/
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
from tools import power_tools               # noqa: F401  find_power_summary_files, compile_power_data, query_power_matrix
from tools import socwatch_tools            # noqa: F401  find_socwatch_files, parse_socwatch_data, query_socwatch_data
from tools import power_rail_knowledge_tools  # noqa: F401  load/get/search power rail knowledge

# ---------------------------------------------------------------------------
# Register prompt
# ---------------------------------------------------------------------------
from prompts import power_socwatch_prompt   # noqa: F401  registers power_socwatch_analysis_prompt


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_or_generate_token(secret_key: str) -> str:
    """Return existing shared token or generate a new one."""
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
    """Return (mcp_instance, auth_token|None)."""
    auth_token = None

    if secure:
        auth_token = get_or_generate_token(settings.SECRET_KEY)
        verifier = StaticTokenVerifier(
            tokens={
                auth_token: {
                    "client_id": "mcp-power-socwatch-client",
                    "scopes": ["read:data", "write:data", "execute:tools"],
                }
            },
            required_scopes=["read:data"],
        )
        app.mcp = FastMCP(name="Power + SocWatch Analysis Server", auth=verifier)

        import importlib
        importlib.reload(power_tools)
        importlib.reload(socwatch_tools)
        importlib.reload(power_rail_knowledge_tools)
        importlib.reload(power_socwatch_prompt)

    return app.mcp, auth_token


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Power + SocWatch Combined MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/power_socwatch_server.py                  # default HTTP on port 8000
  python src/power_socwatch_server.py --port 8080      # custom port
  python src/power_socwatch_server.py --sse            # SSE transport
  python src/power_socwatch_server.py --secure         # enable JWT auth
        """,
    )
    parser.add_argument("--secure", action="store_true", help="Enable JWT token authentication")
    parser.add_argument("--sse", action="store_true", help="Use SSE transport (default: Streamable HTTP)")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("POWER_SOCWATCH_SERVER_PORT", "8000")),
        help="Port to listen on (default: 8000 or POWER_SOCWATCH_SERVER_PORT env var)",
    )
    args = parser.parse_args()

    mcp_instance, auth_token = initialize_mcp_with_auth(secure=args.secure)
    transport = "sse" if args.sse else "http"
    host = settings.HOST
    port = args.port

    print("=" * 60)
    print("  Power + SocWatch Combined MCP Server")
    print("=" * 60)
    print(f"  Environment  : {settings.ENVIRONMENT}")
    print(f"  Transport    : {'SSE' if args.sse else 'HTTP (Streamable)'}")
    print(f"  Host         : {host}:{port}")
    print(f"  MCP Endpoint : http://{host}:{port}/mcp")
    print(f"  Auth         : {'ENABLED' if args.secure else 'DISABLED'}")
    print()
    print("  Power tools  : find_power_summary_files, compile_power_data,")
    print("                 query_power_matrix")
    print("  SocWatch tools: find_socwatch_files, parse_socwatch_data,")
    print("                  query_socwatch_data")
    print("  KB tools     : load_power_rail_knowledge_to_mongodb,")
    print("                 search_power_rail_knowledge")
    print("  Prompts      : power_socwatch_analysis_prompt")
    print("=" * 60)

    if args.secure and auth_token:
        token_file = project_root / ".mcp-token"
        if not token_file.exists():
            old_umask = os.umask(0o177)
            try:
                token_file.write_text(auth_token)
                os.chmod(token_file, 0o600)
            finally:
                os.umask(old_umask)
            print(f"\nToken saved to  : {token_file}")
        else:
            print(f"\nToken loaded from: {token_file}")
        print(f"Authorization  : Bearer {auth_token}\n")

    mcp_instance.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    main()
