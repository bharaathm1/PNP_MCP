"""
File Manager - File system resources.

This module provides access to file system resources through MCP.
"""

from app import mcp
from pathlib import Path
from config.settings import settings
import json


@mcp.resource(
    uri="file://data/readme",
    name="Data Directory README",
    description="README file for the data directory",
    mime_type="text/markdown",
    tags={"file", "documentation"}
)
def get_data_readme() -> str:
    """Return README content for data directory."""
    return """# Data Directory

This directory contains data files used by the MCP Registry server.

## Structure

- `samples/` - Sample data files for demonstration
- `cache/` - Cached data (generated at runtime)
- `logs/` - Server logs
- `uploads/` - User uploaded files

## Usage

Data files can be accessed through MCP resources using the appropriate URIs.

## Notes

- All files should be UTF-8 encoded
- JSON files should be properly formatted
- Binary files are base64 encoded when served
"""


@mcp.resource(
    uri="file://list/{path*}",
    name="List Directory Contents",
    description="List files and directories at the specified path",
    mime_type="application/json",
    tags={"file", "directory", "template"}
)
def list_directory(path: str = "") -> dict:
    """List contents of a directory within the data directory."""
    try:
        base_path = settings.DATA_DIR
        target_path = base_path / path if path else base_path
        
        if not target_path.exists():
            return {
                "error": "Path not found",
                "path": path
            }
        
        if not target_path.is_dir():
            return {
                "error": "Path is not a directory",
                "path": path
            }
        
        # List directory contents
        contents = []
        for item in target_path.iterdir():
            contents.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
                "modified": item.stat().st_mtime
            })
        
        return {
            "path": path,
            "items": sorted(contents, key=lambda x: (x["type"] != "directory", x["name"])),
            "count": len(contents)
        }
    
    except Exception as e:
        return {
            "error": str(e),
            "path": path
        }


@mcp.resource(
    uri="file://content/{filename}",
    name="Get File Content",
    description="Read the content of a specific file",
    mime_type="text/plain",
    tags={"file", "content", "template"}
)
def get_file_content(filename: str) -> str:
    """Read and return file content from the data directory."""
    try:
        file_path = settings.DATA_DIR / filename
        
        if not file_path.exists():
            return f"Error: File '{filename}' not found"
        
        if not file_path.is_file():
            return f"Error: '{filename}' is not a file"
        
        # Check file size
        if file_path.stat().st_size > settings.MAX_RESOURCE_SIZE:
            return f"Error: File too large (max {settings.MAX_RESOURCE_SIZE} bytes)"
        
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    except UnicodeDecodeError:
        return f"Error: '{filename}' is not a text file or has unsupported encoding"
    except Exception as e:
        return f"Error reading file: {str(e)}"


@mcp.resource(
    uri="file://stats/{filename}",
    name="Get File Statistics",
    description="Get statistics about a specific file",
    mime_type="application/json",
    tags={"file", "stats", "template"}
)
def get_file_stats(filename: str) -> dict:
    """Get statistics about a file."""
    try:
        file_path = settings.DATA_DIR / filename
        
        if not file_path.exists():
            return {
                "error": "File not found",
                "filename": filename
            }
        
        stat = file_path.stat()
        
        return {
            "filename": filename,
            "size_bytes": stat.st_size,
            "size_kb": round(stat.st_size / 1024, 2),
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "accessed": stat.st_atime,
            "is_file": file_path.is_file(),
            "is_directory": file_path.is_dir(),
            "extension": file_path.suffix
        }
    
    except Exception as e:
        return {
            "error": str(e),
            "filename": filename
        }
