"""
MCP Registry Server - Main server file using FastMCP with HTTP transport.

This server hosts tools, prompts, and resources using the Model Context Protocol.
It uses Streamable HTTP for network-based communication with clients.
"""

import sys
import argparse
import secrets
import os
from pathlib import Path

# Add src and parent directory to Python path
src_dir = Path(__file__).parent
project_root = src_dir.parent
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))

# Set up AutoBots SDK path BEFORE importing pnp_tool
_WORKSPACE_ROOT = project_root.parent.parent
SDK_WORKING_PATH = os.path.join(_WORKSPACE_ROOT, "applications.services.design-system.autobots.autobots-sdk_new_version")
CRT_WORKING_PATH = os.path.join(_WORKSPACE_ROOT, "crt")
PNP_AGENTS_PATH = os.path.join(_WORKSPACE_ROOT, "PnP_agents")
sys.path.insert(0, SDK_WORKING_PATH)
sys.path.insert(0, PNP_AGENTS_PATH)
os.environ["AUTOBOTS_SDK_TOOL_PATH"] = SDK_WORKING_PATH
os.environ["AUTOBOTS_CONFIG_PATH"] = CRT_WORKING_PATH

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from config.settings import settings
import app

# Import and register tools
from tools import adk_tools
from tools import etl_knowledge_tools
from tools import power_rail_knowledge_tools
from tools import speed_etl_code_tools
from tools import code_execution_tools
from tools import socwatch_tools
from tools import etl_tools
from tools import power_tools

# Import and register prompts
from prompts import mcp_prompt, adk_session_prompt
from prompts import power_prompt

# Import and register resources
from resources import data_sources, file_manager, api_endpoints


def get_or_generate_token(secret_key: str) -> str:
    """
    Get the auth token from .mcp-token file if it exists, otherwise generate one.
    
    Args:
        secret_key: The secret key to base the token on (used if generating)
        
    Returns:
        The auth token string
    """
    token_file = project_root / ".mcp-token"
    
    if token_file.exists():
        # Read token from file
        with open(token_file, 'r') as f:
            token = f.read().strip()
        if token:
            return token
    
    # Generate token if file doesn't exist or is empty
    return generate_secure_token(secret_key)


def generate_secure_token(secret_key: str) -> str:
    """
    Generate a deterministic token based on the secret key.
    This ensures the token remains the same across server restarts
    as long as the secret key doesn't change.
    
    Args:
        secret_key: The secret key to base the token on
        
    Returns:
        A deterministic token string
    """
    import hashlib
    # Create a deterministic token by hashing the secret key
    token_hash = hashlib.sha256(secret_key.encode()).hexdigest()
    return f"mcp-token-{token_hash[:32]}"


def initialize_mcp_with_auth(secure: bool = False) -> tuple[FastMCP, str | None]:
    """
    Initialize or reconfigure the FastMCP server with optional authentication.
    
    Args:
        secure: Whether to enable JWT token authentication
        
    Returns:
        Tuple of (mcp_instance, auth_token or None)
    """
    auth_token = None
    
    if secure:
        # Use the secret key from settings for deterministic token generation
        # Try to read from .mcp-token file first, generate if not present
        auth_token = get_or_generate_token(settings.SECRET_KEY)
        
        # Create a static token verifier for simple authentication
        verifier = StaticTokenVerifier(
            tokens={
                auth_token: {
                    "client_id": "mcp-client",
                    "scopes": ["read:data", "write:data", "execute:tools"]
                }
            },
            required_scopes=["read:data"]
        )
        
        # Create a new MCP instance with authentication
        app.mcp = FastMCP(
            name=settings.SERVER_NAME,
            auth=verifier
        )
        
        # Re-import modules to register with the new authenticated mcp instance
        import importlib
        from tools import adk_tools
        from tools import etl_knowledge_tools
        from tools import power_rail_knowledge_tools
        from tools import speed_etl_code_tools
        from tools import socwatch_tools
        from tools import etl_tools
        from tools import power_tools
        from prompts import mcp_prompt, adk_session_prompt
        from prompts import power_prompt
        from resources import data_sources, file_manager, api_endpoints
        
        # Reload modules to re-register with new mcp instance
        importlib.reload(adk_tools)
        importlib.reload(etl_knowledge_tools)
        importlib.reload(power_rail_knowledge_tools)
        importlib.reload(speed_etl_code_tools)
        importlib.reload(socwatch_tools)
        importlib.reload(etl_tools)
        importlib.reload(power_tools)
        importlib.reload(mcp_prompt)
        importlib.reload(power_prompt)
        importlib.reload(adk_session_prompt)
        importlib.reload(data_sources)
        importlib.reload(file_manager)
        importlib.reload(api_endpoints)
    
    return app.mcp, auth_token


def main():
    """Run the MCP server with HTTP transport (default) or SSE transport."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="MCP Registry Server")
    parser.add_argument(
        "--secure",
        action="store_true",
        help="Enable JWT token authentication"
    )
    parser.add_argument(
        "--sse",
        action="store_true",
        help="Use SSE transport instead of HTTP (default)"
    )
    args = parser.parse_args()
    
    # Initialize MCP with authentication if requested
    mcp, auth_token = initialize_mcp_with_auth(secure=args.secure)
    
    # Determine transport type
    transport = "sse" if args.sse else "http"
    
    # Print server information
    print(f"Starting {settings.SERVER_NAME}...")
    print(f"Environment: {settings.ENVIRONMENT}")
    print(f"Transport: {'SSE' if args.sse else 'HTTP (Streamable)'}")
    print(f"Host: {settings.HOST}:{settings.PORT}")
    print(f"MCP Endpoint: http://{settings.HOST}:{settings.PORT}/mcp")
    print(f"Authentication: {'ENABLED' if args.secure else 'DISABLED'}")
    
    if args.secure and auth_token:
        # Write token to .mcp-token file with owner-only permissions (600)
        # Only create if it doesn't already exist (setup.sh may have created it)
        token_file = project_root / ".mcp-token"
        token_file_created = False
        
        if not token_file.exists():
            # Create file with restrictive permissions (owner read/write only)
            old_umask = os.umask(0o177)  # Set umask to create file with 600 permissions
            try:
                with open(token_file, 'w') as f:
                    f.write(auth_token)
                # Explicitly set permissions to 600 (owner read/write only)
                os.chmod(token_file, 0o600)
                token_file_created = True
            finally:
                os.umask(old_umask)  # Restore original umask
        
        print("\n" + "="*70)
        print("🔐 AUTHENTICATION ENABLED")
        print("="*70)
        if token_file_created:
            print(f"\nToken generated and saved to: {token_file}")
        else:
            print(f"\nToken loaded from: {token_file}")
        print("(File permissions: owner read/write only)")
        print("\nClients must include this token in the Authorization header:")
        print(f"\n  Authorization: Bearer {auth_token}")
        print("\nExample curl command:")
        print(f'  curl -H "Authorization: Bearer {auth_token}" \\')
        print(f"       http://{settings.HOST}:{settings.PORT}/mcp")
        print("\n" + "="*70 + "\n")
    
    # Run with configured transport
    mcp.run(
        transport=transport,
        host=settings.HOST,
        port=settings.PORT
    )


if __name__ == "__main__":
    main()
