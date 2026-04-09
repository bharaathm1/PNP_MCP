"""
Data Sources - Expose various data sources as MCP resources.

This module provides access to different data sources through
MCP resource URIs.
"""

from app import mcp
from typing import Annotated
from pydantic import Field
import json
from datetime import datetime


@mcp.resource(
    uri="data://server/info",
    name="Server Information",
    description="Basic information about the MCP server",
    mime_type="application/json",
    tags={"server", "info"}
)
def get_server_info() -> dict:
    """Return basic server information."""
    return {
        "name": "MCP Registry Server",
        "version": "1.0.0",
        "description": "A comprehensive MCP server with tools, prompts, and resources",
        "transport": "SSE",
        "uptime_start": datetime.now().isoformat(),
        "capabilities": {
            "tools": True,
            "prompts": True,
            "resources": True
        }
    }


@mcp.resource(
    uri="data://server/stats",
    name="Server Statistics",
    description="Runtime statistics of the server",
    mime_type="application/json",
    tags={"server", "monitoring"}
)
async def get_server_stats() -> dict:
    """Return server runtime statistics."""
    # In a real implementation, you would track these metrics
    return {
        "requests_processed": 0,
        "tools_called": 0,
        "prompts_generated": 0,
        "resources_accessed": 0,
        "uptime_seconds": 0,
        "last_request": datetime.now().isoformat()
    }


@mcp.resource(
    uri="data://sample/users",
    name="Sample User Data",
    description="Sample user data for demonstration",
    mime_type="application/json",
    tags={"sample", "data"}
)
def get_sample_users() -> list:
    """Return sample user data."""
    return [
        {
            "id": 1,
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "role": "Admin",
            "active": True
        },
        {
            "id": 2,
            "name": "Bob Smith",
            "email": "bob@example.com",
            "role": "User",
            "active": True
        },
        {
            "id": 3,
            "name": "Charlie Brown",
            "email": "charlie@example.com",
            "role": "User",
            "active": False
        }
    ]


@mcp.resource(
    uri="data://sample/products",
    name="Sample Product Catalog",
    description="Sample product catalog data",
    mime_type="application/json",
    tags={"sample", "data", "catalog"}
)
def get_sample_products() -> list:
    """Return sample product catalog."""
    return [
        {
            "id": "PROD-001",
            "name": "Laptop Pro 15",
            "category": "Electronics",
            "price": 1299.99,
            "in_stock": True,
            "specs": {
                "ram": "16GB",
                "storage": "512GB SSD",
                "processor": "Intel i7"
            }
        },
        {
            "id": "PROD-002",
            "name": "Wireless Mouse",
            "category": "Accessories",
            "price": 29.99,
            "in_stock": True,
            "specs": {
                "connectivity": "Bluetooth",
                "battery": "AA"
            }
        },
        {
            "id": "PROD-003",
            "name": "Mechanical Keyboard",
            "category": "Accessories",
            "price": 149.99,
            "in_stock": False,
            "specs": {
                "switches": "Cherry MX Blue",
                "backlight": "RGB"
            }
        }
    ]


@mcp.resource(
    uri="data://config/{category}",
    name="Configuration by Category",
    description="Get configuration data by category",
    mime_type="application/json",
    tags={"config", "template"}
)
def get_config_by_category(category: str) -> dict:
    """Return configuration data for a specific category."""
    configs = {
        "database": {
            "host": "localhost",
            "port": 5432,
            "name": "mcp_registry",
            "pool_size": 10
        },
        "cache": {
            "enabled": True,
            "ttl_seconds": 300,
            "max_size_mb": 100
        },
        "logging": {
            "level": "INFO",
            "format": "json",
            "output": "stdout"
        },
        "api": {
            "rate_limit": 100,
            "timeout_seconds": 30,
            "max_retries": 3
        }
    }
    
    if category not in configs:
        return {
            "error": f"Category '{category}' not found",
            "available_categories": list(configs.keys())
        }
    
    return {
        "category": category,
        "config": configs[category]
    }
