"""
Configuration settings for the MCP Registry server.

Environment variables can be used to override these settings:
- SERVER_NAME: Name of the MCP server
- SERVER_HOST: Host address to bind to
- SERVER_PORT: Port number to listen on
- ENVIRONMENT: development, staging, or production
"""

import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()





class Settings:
    """Server configuration settings."""
    
    # Server Information
    SERVER_NAME = os.getenv("SERVER_NAME", "MCP Registry Server")
    VERSION = "1.0.0"
    
    # Network Configuration
    HOST = os.getenv("SERVER_HOST", "0.0.0.0")
    PORT = int(os.getenv("SERVER_PORT", "11020"))
    
    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = ENVIRONMENT == "development"
    
    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", "default-insecure-key-change-in-production")
    
    # Worker Configuration (for production deployment)
    WORKERS = int(os.getenv("WORKERS", "1"))  # Number of uvicorn workers
    # Recommended: 2-4 workers per CPU core for I/O bound tasks
    # Formula: (2 x CPU cores) + 1
    
    # Paths
    ROOT_DIR = Path(__file__).parent.parent
    DATA_DIR = ROOT_DIR / "data"
    LOGS_DIR = ROOT_DIR / "logs"
    
    # MCP Configuration
    MASK_ERROR_DETAILS = ENVIRONMENT == "production"
    ON_DUPLICATE_TOOLS = "warn"
    ON_DUPLICATE_PROMPTS = "warn"
    ON_DUPLICATE_RESOURCES = "warn"
    
    # Transport Settings (SSE)
    SSE_HEARTBEAT_INTERVAL = 30  # seconds
    SSE_MAX_CONNECTIONS = 100
    
    # Resource Limits
    MAX_TOOL_EXECUTION_TIME = 300  # seconds
    MAX_RESOURCE_SIZE = 10 * 1024 * 1024  # 10MB
    
    def __init__(self):
        """Ensure required directories exist."""
        self.DATA_DIR.mkdir(exist_ok=True)
        self.LOGS_DIR.mkdir(exist_ok=True)


# Global settings instance
settings = Settings()
