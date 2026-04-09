"""
Helper utilities for MCP Registry.

Provides common helper functions.
"""

import json
from typing import Any, Dict
from datetime import datetime
import hashlib


def format_timestamp(timestamp: float = None) -> str:
    """
    Format a timestamp as ISO 8601 string.
    
    Args:
        timestamp: Unix timestamp (uses current time if None)
        
    Returns:
        ISO 8601 formatted string
    """
    if timestamp is None:
        dt = datetime.now()
    else:
        dt = datetime.fromtimestamp(timestamp)
    
    return dt.isoformat()


def safe_json_dumps(data: Any, indent: int = 2) -> str:
    """
    Safely serialize data to JSON string.
    
    Args:
        data: Data to serialize
        indent: Indentation level
        
    Returns:
        JSON string or error message
    """
    try:
        return json.dumps(data, indent=indent, default=str)
    except (TypeError, ValueError) as e:
        return f'{{"error": "Failed to serialize data: {str(e)}"}}'


def safe_json_loads(json_str: str) -> Dict[str, Any]:
    """
    Safely parse JSON string.
    
    Args:
        json_str: JSON string to parse
        
    Returns:
        Parsed data or error dict
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse JSON: {str(e)}"}


def generate_request_id() -> str:
    """
    Generate a unique request ID.
    
    Returns:
        Unique request ID string
    """
    timestamp = datetime.now().isoformat()
    hash_obj = hashlib.sha256(timestamp.encode())
    return hash_obj.hexdigest()[:16]


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate a string to maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to append if truncated
        
    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def format_bytes(bytes_count: int) -> str:
    """
    Format byte count as human-readable string.
    
    Args:
        bytes_count: Number of bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.2f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.2f} PB"


def merge_dicts(*dicts: Dict) -> Dict:
    """
    Merge multiple dictionaries, with later dicts taking precedence.
    
    Args:
        *dicts: Dictionaries to merge
        
    Returns:
        Merged dictionary
    """
    result = {}
    for d in dicts:
        result.update(d)
    return result


def chunk_list(items: list, chunk_size: int) -> list:
    """
    Split a list into chunks of specified size.
    
    Args:
        items: List to chunk
        chunk_size: Size of each chunk
        
    Returns:
        List of chunks
    """
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
