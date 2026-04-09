"""
System Information Tools - Retrieve system and environment information.

This module provides tools to get information about the system,
environment, and runtime.
"""

from app import mcp
from typing import Annotated
from pydantic import Field
from utils.decorators import embed_response, embed_if_large, embed_with_metadata, metadata
import platform
import os
import sys
from datetime import datetime


@mcp.tool(
    description="Get operating system information",
    tags={"system", "info"}
)

@embed_with_metadata(chunk_size=200, top_k=5, chunk_overlap=200)
@metadata(source="platform module", description="Operating system details and system logs")
def get_os_info() -> dict:
    """Return information about the operating system."""
    
    # Get actual OS information
    os_details = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "platform": platform.platform()
    }
    
    # Generate dummy log output
    large_text = "\n".join([
        f"[2024-11-25 10:{i:02d}:00] INFO: Processing batch {i} of 1000"
        f" - Status: {'SUCCESS' if i % 3 == 0 else 'PENDING'}"
        f" - Records: {i * 100} - Memory: {i * 2}MB"
        for i in range(50)
    ])
    
    # Combine both
    return {
        "os_info": os_details,
        "system_logs": large_text
    }


@mcp.tool(
    description="Get Python runtime information",
    tags={"system", "info", "python"}
)
def get_python_info() -> dict:
    """Return information about the Python runtime."""
    return {
        "version": sys.version,
        "version_info": {
            "major": sys.version_info.major,
            "minor": sys.version_info.minor,
            "micro": sys.version_info.micro
        },
        "executable": sys.executable,
        "platform": sys.platform,
        "prefix": sys.prefix
    }


@mcp.tool(
    description="Get current timestamp and date/time information",
    tags={"system", "time"}
)
def get_current_time(
    format: Annotated[str, Field(
        description="Time format: 'iso' or 'unix'",
        default="iso"
    )] = "iso"
) -> dict:
    """Get current date and time in various formats."""
    now = datetime.now()
    
    result = {
        "timestamp": now.isoformat(),
        "unix": int(now.timestamp()),
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "hour": now.hour,
        "minute": now.minute,
        "second": now.second
    }
    
    return result


@mcp.tool(
    description="List environment variables (filtered by prefix)",
    tags={"system", "environment"}
)
def list_env_variables(
    prefix: Annotated[str, Field(
        description="Filter variables by prefix (e.g., 'PATH', 'PYTHON')",
        default=""
    )] = ""
) -> dict:
    """List environment variables, optionally filtered by prefix."""
    env_vars = {}
    for key, value in os.environ.items():
        if prefix.upper() in key.upper():
            env_vars[key] = value
    
    return {
        "count": len(env_vars),
        "prefix_filter": prefix if prefix else "none",
        "variables": env_vars
    }


@mcp.tool(
    description="Get system resource usage statistics",
    tags={"system", "monitoring"}
)
def get_system_stats() -> dict:
    """Get basic system resource statistics."""
    import psutil
    
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return {
        "cpu": {
            "percent": cpu_percent,
            "count": psutil.cpu_count()
        },
        "memory": {
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "percent": memory.percent
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent": disk.percent
        }
    }


# Example: Tool that always returns large content that should be embedded
@mcp.tool(
    description="Get detailed system logs (large output - will be embedded)",
    tags={"system", "logs", "monitoring"}
)
@embed_response
def get_system_logs() -> str:
    """
    Generate detailed system logs.
    
    This tool demonstrates the @embed_response decorator which signals
    to the client that the response should be embedded rather than
    sent directly to the LLM.
    """
    # Generate large text (simulate log file)
    large_text = "\n".join([
        f"[2024-11-25 10:{i:02d}:00] INFO: Processing batch {i} of 1000"
        f" - Status: {'SUCCESS' if i % 3 == 0 else 'PENDING'}"
        f" - Records: {i * 100} - Memory: {i * 2}MB"
        for i in range(10)
    ])
    
    return large_text


# Example: Tool that conditionally embeds based on size
@mcp.tool(
    description="Get process list with optional detail level",
    tags={"system", "processes"}
)
@embed_if_large(threshold=2000)
def get_process_list(
    detailed: Annotated[bool, Field(
        description="Include detailed process information",
        default=False
    )] = False
) -> str:
    """
    List running processes.
    
    This tool demonstrates the @embed_if_large decorator which only
    signals for embedding if the response exceeds the threshold.
    """
    import psutil
    
    if detailed:
        # Generate detailed output that will trigger embedding
        output = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_percent', 'cpu_percent']):
            try:
                info = proc.info
                output.append(
                    f"PID: {info['pid']:6d} | "
                    f"Name: {info['name']:30s} | "
                    f"User: {info['username']:15s} | "
                    f"Memory: {info['memory_percent']:6.2f}% | "
                    f"CPU: {info['cpu_percent']:6.2f}%"
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return "\n".join(output)
    else:
        # Generate brief output that won't trigger embedding
        return f"Total processes: {len(psutil.pids())}"


# Example: Tool with custom embedding metadata
@mcp.tool(
    description="Get system configuration file",
    tags={"system", "config"}
)
@embed_with_metadata(content_type="config", format="json", source="system", chunk_size=1024, top_k=5)
def get_system_config() -> dict:
    """
    Get system configuration.
    
    This tool demonstrates the @embed_with_metadata decorator which
    adds custom metadata to help the client determine embedding strategy.
    """
    return {
        "hostname": platform.node(),
        "system": platform.system(),
        "architecture": platform.machine(),
        "python_version": sys.version,
        "environment": dict(os.environ)
    }


# Example: Async tool showcasing async capabilities
@mcp.tool(
    description="Perform async system health check with multiple concurrent operations",
    tags={"system", "async", "health"}
)
async def async_system_health_check(
    include_network: Annotated[bool, Field(
        description="Include network connectivity check",
        default=True
    )] = True,
    timeout_seconds: Annotated[int, Field(
        description="Timeout for async operations in seconds",
        default=5,
        ge=1,
        le=30
    )] = 5
) -> dict:
    """
    Perform an asynchronous system health check.
    
    This tool demonstrates async capabilities by running multiple
    checks concurrently using asyncio. It performs:
    - CPU and memory checks
    - Disk space checks
    - Optional network connectivity checks
    
    All checks run concurrently for better performance.
    """
    import asyncio
    import psutil
    
    async def check_cpu() -> dict:
        """Async CPU check - simulates async I/O bound operation."""
        await asyncio.sleep(0.1)  # Simulate async operation
        return {
            "status": "healthy" if psutil.cpu_percent(interval=0.1) < 90 else "warning",
            "usage_percent": psutil.cpu_percent(interval=0.1),
            "core_count": psutil.cpu_count(),
            "frequency_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else None
        }
    
    async def check_memory() -> dict:
        """Async memory check."""
        await asyncio.sleep(0.1)  # Simulate async operation
        memory = psutil.virtual_memory()
        return {
            "status": "healthy" if memory.percent < 85 else "warning",
            "usage_percent": memory.percent,
            "available_gb": round(memory.available / (1024**3), 2),
            "total_gb": round(memory.total / (1024**3), 2)
        }
    
    async def check_disk() -> dict:
        """Async disk check."""
        await asyncio.sleep(0.1)  # Simulate async operation
        disk = psutil.disk_usage('/')
        return {
            "status": "healthy" if disk.percent < 90 else "warning",
            "usage_percent": disk.percent,
            "free_gb": round(disk.free / (1024**3), 2),
            "total_gb": round(disk.total / (1024**3), 2)
        }
    
    async def check_network() -> dict:
        """Async network connectivity check."""
        import socket
        await asyncio.sleep(0.1)  # Simulate async operation
        try:
            # Check if we can resolve DNS
            socket.gethostbyname("google.com")
            net_io = psutil.net_io_counters()
            return {
                "status": "healthy",
                "dns_resolution": "ok",
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv
            }
        except socket.gaierror:
            return {
                "status": "unhealthy",
                "dns_resolution": "failed",
                "error": "DNS resolution failed"
            }
    
    # Build list of tasks to run concurrently
    tasks = [
        check_cpu(),
        check_memory(),
        check_disk()
    ]
    
    if include_network:
        tasks.append(check_network())
    
    # Run all checks concurrently with timeout
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        return {
            "status": "error",
            "error": f"Health check timed out after {timeout_seconds} seconds"
        }
    
    # Process results
    cpu_result, memory_result, disk_result = results[:3]
    network_result = results[3] if include_network and len(results) > 3 else None
    
    # Handle any exceptions in results
    def safe_result(result, name):
        if isinstance(result, Exception):
            return {"status": "error", "error": str(result)}
        return result
    
    health_report = {
        "timestamp": datetime.now().isoformat(),
        "overall_status": "healthy",
        "checks": {
            "cpu": safe_result(cpu_result, "cpu"),
            "memory": safe_result(memory_result, "memory"),
            "disk": safe_result(disk_result, "disk")
        }
    }
    
    if include_network and network_result:
        health_report["checks"]["network"] = safe_result(network_result, "network")
    
    # Determine overall status
    all_statuses = [
        check.get("status", "unknown") 
        for check in health_report["checks"].values()
        if isinstance(check, dict)
    ]
    
    if "error" in all_statuses or "unhealthy" in all_statuses:
        health_report["overall_status"] = "unhealthy"
    elif "warning" in all_statuses:
        health_report["overall_status"] = "warning"
    
    return health_report

