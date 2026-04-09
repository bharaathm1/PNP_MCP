"""
Validation utilities for MCP Registry.

Provides common validation functions.
"""

import re
from typing import Any, Optional
from pathlib import Path


def validate_uri(uri: str) -> bool:
    """
    Validate a MCP resource URI format.
    
    Args:
        uri: URI to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Basic URI pattern: scheme://path
    pattern = r'^[a-zA-Z][a-zA-Z0-9+.-]*://[^\s]*$'
    return bool(re.match(pattern, uri))


def validate_file_path(path: str, base_dir: Path) -> bool:
    """
    Validate that a file path is within the base directory.
    
    Args:
        path: File path to validate
        base_dir: Base directory that should contain the path
        
    Returns:
        True if path is safe, False otherwise
    """
    try:
        full_path = (base_dir / path).resolve()
        return full_path.is_relative_to(base_dir.resolve())
    except (ValueError, RuntimeError):
        return False


def validate_json_schema(data: Any, required_fields: list[str]) -> tuple[bool, Optional[str]]:
    """
    Validate that data contains required fields.
    
    Args:
        data: Data to validate (should be dict)
        required_fields: List of required field names
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, "Data must be a dictionary"
    
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    
    return True, None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing unsafe characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove path separators and other unsafe characters
    unsafe_chars = ['/', '\\', '..', '\x00', '\n', '\r', '\t']
    sanitized = filename
    
    for char in unsafe_chars:
        sanitized = sanitized.replace(char, '_')
    
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip('. ')
    
    return sanitized or "unnamed_file"


def validate_port(port: int) -> bool:
    """
    Validate that a port number is in valid range.
    
    Args:
        port: Port number
        
    Returns:
        True if valid, False otherwise
    """
    return 1 <= port <= 65535


def validate_parameter_type(value: Any, expected_type: type) -> bool:
    """
    Validate that a value matches the expected type.
    
    Args:
        value: Value to check
        expected_type: Expected type
        
    Returns:
        True if type matches, False otherwise
    """
    return isinstance(value, expected_type)
