"""
Logging utilities for MCP Registry.

Provides structured logging for the MCP server with:
- Detailed request/response logging
- Tool execution tracking with timing
- Resource access monitoring
- Color-coded console output
- JSON structured logging option
"""

import logging
import sys
import json
import time
import traceback
from pathlib import Path
from datetime import datetime
from typing import Any, Optional, Dict
from functools import wraps
from config.settings import settings


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info) if record.exc_info[0] else None
            }
        
        return json.dumps(log_data)


def setup_logger(name: str = "mcp-registry", json_format: bool = False) -> logging.Logger:
    """
    Set up and configure a logger for the application.
    
    Args:
        name: Logger name
        json_format: If True, use JSON formatting for file logs
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    # Set level based on environment
    level = logging.DEBUG if settings.DEBUG else logging.INFO
    logger.setLevel(level)
    
    # Console handler — MUST use stderr, not stdout.
    # In stdio MCP servers, stdout is the JSON-RPC transport wire.
    # Any text written to stdout (including log lines) corrupts the
    # protocol framing and causes VS Code to drop all tool registrations.
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        '%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # File handler - regular log
    log_file = settings.LOGS_DIR / f"mcp-registry-{datetime.now():%Y%m%d}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)  # Capture all levels in file
    
    if json_format:
        file_handler.setFormatter(JSONFormatter())
    else:
        file_formatter = logging.Formatter(
            '%(asctime)s │ %(levelname)-8s │ %(name)s │ %(module)s.%(funcName)s:%(lineno)d │ %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
    
    # Separate file for errors only
    error_log_file = settings.LOGS_DIR / f"mcp-errors-{datetime.now():%Y%m%d}.log"
    error_handler = logging.FileHandler(error_log_file)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        '%(asctime)s │ %(levelname)s │ %(name)s │ %(module)s.%(funcName)s:%(lineno)d\n%(message)s\n',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    
    return logger


# Global logger instance
logger = setup_logger()

# Create specialized loggers
request_logger = setup_logger("mcp.requests")
tool_logger = setup_logger("mcp.tools")
resource_logger = setup_logger("mcp.resources")
prompt_logger = setup_logger("mcp.prompts")
auth_logger = setup_logger("mcp.auth")


def log_mcp_request(method: str, client_ip: str, path: str, 
                    request_id: Optional[str] = None,
                    user_agent: Optional[str] = None,
                    content_type: Optional[str] = None,
                    body_preview: Optional[str] = None):
    """Log incoming MCP request with details."""
    msg_parts = [
        f"REQUEST",
        f"method={method}",
        f"path={path}",
        f"client={client_ip}",
    ]
    if request_id:
        msg_parts.append(f"req_id={request_id}")
    if user_agent:
        msg_parts.append(f"ua={user_agent[:50]}")
    if body_preview:
        msg_parts.append(f"body={body_preview[:100]}")
    
    request_logger.info(" │ ".join(msg_parts))


def log_mcp_response(status_code: int, client_ip: str, path: str,
                     duration_ms: float, request_id: Optional[str] = None,
                     response_type: Optional[str] = None):
    """Log MCP response with timing."""
    msg_parts = [
        f"RESPONSE",
        f"status={status_code}",
        f"path={path}",
        f"client={client_ip}",
        f"duration={duration_ms:.2f}ms",
    ]
    if request_id:
        msg_parts.append(f"req_id={request_id}")
    if response_type:
        msg_parts.append(f"type={response_type}")
    
    request_logger.info(" │ ".join(msg_parts))


def log_tool_call(tool_name: str, params: dict, request_id: Optional[str] = None):
    """Log a tool call with parameters."""
    params_str = json.dumps(params, default=str)[:200]  # Truncate long params
    msg = f"🔧 TOOL_CALL │ tool={tool_name} │ params={params_str}"
    if request_id:
        msg += f" │ req_id={request_id}"
    tool_logger.info(msg)


def log_tool_result(tool_name: str, success: bool, duration_ms: float,
                    result_preview: Optional[str] = None,
                    error: Optional[str] = None,
                    request_id: Optional[str] = None):
    """Log tool execution result with timing."""
    status = "SUCCESS" if success else "FAILED"
    msg = f"TOOL_RESULT │ tool={tool_name} │ status={status} │ duration={duration_ms:.2f}ms"
    
    if result_preview and success:
        msg += f" │ result={result_preview[:100]}"
    if error:
        msg += f" │ error={error}"
    if request_id:
        msg += f" │ req_id={request_id}"
    
    if success:
        tool_logger.info(msg)
    else:
        tool_logger.error(msg)


def log_prompt_generation(prompt_name: str, params: dict, request_id: Optional[str] = None):
    """Log a prompt generation with parameters."""
    params_str = json.dumps(params, default=str)[:200]
    msg = f"PROMPT │ prompt={prompt_name} │ params={params_str}"
    if request_id:
        msg += f" │ req_id={request_id}"
    prompt_logger.info(msg)


def log_resource_access(resource_uri: str, success: bool = True, 
                        size_bytes: Optional[int] = None,
                        request_id: Optional[str] = None):
    """Log a resource access."""
    status = "OK" if success else "FAILED"
    msg = f"RESOURCE │ uri={resource_uri} │ status={status}"
    if size_bytes is not None:
        msg += f" │ size={size_bytes}B"
    if request_id:
        msg += f" │ req_id={request_id}"
    resource_logger.info(msg)


def log_auth_attempt(client_ip: str, success: bool, 
                     client_id: Optional[str] = None,
                     reason: Optional[str] = None):
    """Log authentication attempt."""
    status = "GRANTED" if success else "DENIED"
    msg = f"AUTH │ client={client_ip} │ status={status}"
    if client_id:
        msg += f" │ client_id={client_id}"
    if reason:
        msg += f" │ reason={reason}"
    
    if success:
        auth_logger.info(msg)
    else:
        auth_logger.warning(msg)


def log_error(error: Exception, context: str = "", request_id: Optional[str] = None):
    """Log an error with context."""
    msg = f"ERROR │ type={type(error).__name__} │ msg={str(error)}"
    if context:
        msg += f" │ context={context}"
    if request_id:
        msg += f" │ req_id={request_id}"
    logger.error(msg, exc_info=True)


def log_server_event(event: str, details: Optional[Dict[str, Any]] = None):
    """Log server lifecycle events."""
    msg = f"🖥️  SERVER │ event={event}"
    if details:
        details_str = " │ ".join(f"{k}={v}" for k, v in details.items())
        msg += f" │ {details_str}"
    logger.info(msg)


def with_logging(func):
    """Decorator to add logging to tool functions."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = func.__name__
        start_time = time.time()
        
        # Log the call
        log_tool_call(tool_name, kwargs if kwargs else dict(zip(func.__code__.co_varnames, args)))
        
        try:
            result = func(*args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000
            result_preview = str(result)[:100] if result is not None else None
            log_tool_result(tool_name, success=True, duration_ms=duration_ms, result_preview=result_preview)
            return result
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_tool_result(tool_name, success=False, duration_ms=duration_ms, error=str(e))
            raise
    
    return wrapper
