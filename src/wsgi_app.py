"""
ASGI Application for Production Deployment with Multiple Workers.

This module creates a standalone ASGI application that can be run with:
    uvicorn src.wsgi_app:app --host 0.0.0.0 --port 11000 --workers 4

For production with gunicorn:
    gunicorn src.wsgi_app:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:11000

Note: This uses http_app() which is stateless by default, making it safe for
multiple workers. This is the recommended approach for scalable production
deployments as per FastMCP documentation.
"""

import sys
import os
from pathlib import Path

# Add src and parent directory to Python path
src_dir = Path(__file__).parent
project_root = src_dir.parent
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))

from fastmcp import FastMCP
from config.settings import settings

# Import logging utilities
from utils.logger import log_server_event, logger
from utils.logging_middleware import add_logging_middleware

# Import and register tools
from pnp_tool import calculator, system_info, text_processing

# Import and register prompts
from prompts import mcp_prompt, adk_session_prompt

# Import and register resources
from resources import data_sources, file_manager, api_endpoints

import app

# ============================================================================
# AUTHENTICATION CONFIGURATION (Optional)
# ============================================================================
# Set ENABLE_AUTH=true in environment to enable authentication
ENABLE_AUTH = os.getenv("ENABLE_AUTH", "false").lower() == "true"
_auth_token = None

if ENABLE_AUTH:
    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
    
    def get_auth_token() -> str:
        """Get auth token from .mcp-token file or environment."""
        # Try environment variable first
        token = os.getenv("MCP_AUTH_TOKEN")
        if token:
            return token
        
        # Try .mcp-token file
        token_file = project_root / ".mcp-token"
        if token_file.exists():
            with open(token_file, 'r') as f:
                token = f.read().strip()
                if token:
                    return token
        
        # Generate deterministic token from secret key
        import hashlib
        token_hash = hashlib.sha256(settings.SECRET_KEY.encode()).hexdigest()
        return f"mcp-token-{token_hash[:32]}"
    
    _auth_token = get_auth_token()
    verifier = StaticTokenVerifier(
        tokens={
            _auth_token: {
                "client_id": "mcp-client",
                "scopes": ["read:data", "write:data", "execute:tools"]
            }
        },
        required_scopes=["read:data"]
    )
    
    # Reinitialize mcp with auth
    app.mcp = FastMCP(
        name=settings.SERVER_NAME,
        auth=verifier
    )
    
    # Reload modules to register with new mcp instance
    import importlib
    importlib.reload(calculator)
    importlib.reload(system_info)
    importlib.reload(text_processing)
    importlib.reload(mcp_prompt)
    importlib.reload(adk_session_prompt)
    importlib.reload(data_sources)
    importlib.reload(file_manager)
    importlib.reload(api_endpoints)

# ============================================================================
# CREATE ASGI APPLICATION
# ============================================================================
# This creates the ASGI app that uvicorn will serve
# Using http_app() for HTTP Streamable transport - recommended for production
# with multiple workers. stateless_http=True is REQUIRED for multi-worker deployments
# as it ensures no session state is shared between workers.

import warnings
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    _base_app = app.mcp.http_app(path="/mcp", stateless_http=True)

# Wrap with logging middleware for detailed request logging
app = add_logging_middleware(_base_app)


# ============================================================================
# STARTUP MESSAGE (only print once from main process)
# ============================================================================
def print_startup_info():
    """Print startup information only once (called by lifespan or main process)."""
    # Check if we're the main process (not a worker)
    # Workers have WORKER_ID env var set by some process managers
    # Or we can check if this is the first time being called
    import multiprocessing
    
    # Use a file lock or environment marker to ensure single print
    marker_file = project_root / ".startup_printed"
    pid = os.getpid()
    
    # Only print if we're likely the main/first process
    # This is a simple heuristic - check parent PID
    try:
        # Try to be the first to create the marker
        if not os.path.exists(marker_file):
            with open(marker_file, 'w') as f:
                f.write(str(pid))
            
            # Clean up marker file on exit
            import atexit
            atexit.register(lambda: os.path.exists(marker_file) and os.remove(marker_file))
            
            return True
    except:
        pass
    return False


# Print startup message only once
if print_startup_info():
    log_server_event("startup", {
        "server": settings.SERVER_NAME,
        "environment": settings.ENVIRONMENT,
        "transport": "HTTP (Streamable)",
        "host": settings.HOST,
        "port": settings.PORT,
        "auth": "ENABLED" if ENABLE_AUTH else "DISABLED"
    })
    
    print(f"\nStarting {settings.SERVER_NAME}...")
    print(f"Environment: {settings.ENVIRONMENT}")
    print(f"Transport: HTTP (Streamable) - Scalable for multiple workers")
    print(f"Host: {settings.HOST}:{settings.PORT}")
    print(f"Authentication: {'ENABLED' if ENABLE_AUTH else 'DISABLED'}")
    print(f"\nMCP Endpoint: http://{settings.HOST}:{settings.PORT}/mcp")
    
    if ENABLE_AUTH and _auth_token:
        print("\n" + "="*70)
        print("🔐 AUTHENTICATION ENABLED")
        print("="*70)
        print("\nClients must include this token in the Authorization header:")
        print(f"\n  Authorization: Bearer {_auth_token}")
        print("\nExample curl command:")
        print(f'  curl -H "Authorization: Bearer {_auth_token}" \\')
        print(f"       http://{settings.HOST}:{settings.PORT}/mcp")
        print("\n" + "="*70)
    
    print("")
