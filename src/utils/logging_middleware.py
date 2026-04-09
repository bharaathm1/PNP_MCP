"""
Logging Middleware for MCP Server.

This middleware intercepts HTTP requests to provide detailed logging
of MCP protocol messages, including tool calls, resource access, and prompts.
"""

import json
import time
import uuid
from typing import Callable, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Send, Scope, Message

from utils.logger import (
    log_mcp_request, 
    log_mcp_response, 
    log_tool_call, 
    log_tool_result,
    log_resource_access,
    log_prompt_generation,
    log_auth_attempt,
    log_error,
    request_logger
)


class MCPLoggingMiddleware:
    """
    ASGI Middleware for comprehensive MCP request logging.
    
    This middleware:
    - Logs all incoming requests with client info
    - Parses MCP JSON-RPC messages to log tool calls, resources, and prompts
    - Tracks request duration
    - Generates unique request IDs for correlation
    """
    
    def __init__(self, app: ASGIApp):
        self.app = app
    
    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Generate request ID
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        # Get client info
        client_ip = self._get_client_ip(scope)
        path = scope.get("path", "")
        method = scope.get("method", "")
        
        # Capture request body for MCP parsing
        body_parts = []
        
        async def receive_wrapper():
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                if body:
                    body_parts.append(body)
            return message
        
        # Track response status
        response_status = [200]
        response_started = [False]
        
        async def send_wrapper(message: Message):
            if message["type"] == "http.response.start":
                response_status[0] = message.get("status", 200)
                response_started[0] = True
            await send(message)
        
        # Log incoming request
        user_agent = self._get_header(scope, "user-agent")
        content_type = self._get_header(scope, "content-type")
        
        try:
            await self.app(scope, receive_wrapper, send_wrapper)
            
            # Parse and log MCP-specific info from captured body
            if body_parts and path == "/mcp":
                body = b"".join(body_parts)
                self._log_mcp_message(body, request_id, client_ip)
            
        except Exception as e:
            log_error(e, context="request_handling", request_id=request_id)
            raise
        finally:
            # Log response
            duration_ms = (time.time() - start_time) * 1000
            log_mcp_response(
                status_code=response_status[0],
                client_ip=client_ip,
                path=path,
                duration_ms=duration_ms,
                request_id=request_id
            )
    
    def _get_client_ip(self, scope: Scope) -> str:
        """Extract client IP from scope, checking X-Forwarded-For header."""
        # Check for forwarded header first (for reverse proxies)
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"x-forwarded-for":
                return header_value.decode().split(",")[0].strip()
            if header_name == b"x-real-ip":
                return header_value.decode()
        
        # Fall back to direct client
        client = scope.get("client")
        if client:
            return client[0]
        return "unknown"
    
    def _get_header(self, scope: Scope, name: str) -> Optional[str]:
        """Get a header value from scope."""
        name_bytes = name.lower().encode()
        for header_name, header_value in scope.get("headers", []):
            if header_name == name_bytes:
                return header_value.decode()
        return None
    
    def _log_mcp_message(self, body: bytes, request_id: str, client_ip: str):
        """Parse and log MCP JSON-RPC message content."""
        try:
            data = json.loads(body.decode())
            
            # Handle both single messages and batches
            messages = data if isinstance(data, list) else [data]
            
            for msg in messages:
                method = msg.get("method", "")
                params = msg.get("params", {})
                msg_id = msg.get("id", "")
                
                # Log based on MCP method type
                if method == "tools/call":
                    tool_name = params.get("name", "unknown")
                    tool_args = params.get("arguments", {})
                    log_tool_call(tool_name, tool_args, request_id)
                    
                elif method == "tools/list":
                    request_logger.debug(f"TOOLS_LIST │ req_id={request_id}")
                    
                elif method == "resources/read":
                    uri = params.get("uri", "unknown")
                    log_resource_access(uri, request_id=request_id)
                    
                elif method == "resources/list":
                    request_logger.debug(f"RESOURCES_LIST │ req_id={request_id}")
                    
                elif method == "prompts/get":
                    prompt_name = params.get("name", "unknown")
                    prompt_args = params.get("arguments", {})
                    log_prompt_generation(prompt_name, prompt_args, request_id)
                    
                elif method == "prompts/list":
                    request_logger.debug(f"📋 PROMPTS_LIST │ req_id={request_id}")
                    
                elif method == "initialize":
                    client_info = params.get("clientInfo", {})
                    request_logger.info(
                        f"INITIALIZE │ client={client_info.get('name', 'unknown')} │ "
                        f"version={client_info.get('version', 'unknown')} │ req_id={request_id}"
                    )
                    
                elif method == "ping":
                    request_logger.debug(f"PING │ req_id={request_id}")
                    
                elif method:
                    # Log other methods at debug level
                    request_logger.debug(f"{method.upper()} │ req_id={request_id}")
                    
        except json.JSONDecodeError:
            # Not JSON, might be SSE or other format
            pass
        except Exception as e:
            # Don't fail on logging errors
            request_logger.debug(f"Failed to parse MCP message: {e}")


def add_logging_middleware(app: ASGIApp) -> ASGIApp:
    """Wrap an ASGI app with logging middleware."""
    return MCPLoggingMiddleware(app)
