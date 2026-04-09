"""
MCP Agent System Prompt - Generic runtime tool integration instructions.
 
This module provides a system prompt for MCP agents that dynamically discover
and use tools at runtime without assuming a fixed toolset.
"""
 
from app import mcp
from typing import Annotated, Optional, Literal
from pydantic import Field
from pathlib import Path
 
@mcp.prompt(
    description=(
        "Generic MCP agent system prompt that teaches the agent to dynamically discover "
        "and use any MCP tools that become available at runtime. The agent learns to inspect "
        "available tools, choose appropriate ones efficiently, and handle cases where tools "
        "cannot fulfill requests."
    ),
    tags={"mcp", "agent", "runtime", "dynamic-tools", "generic"}
)
def mcp_server_prompt() -> str:
    """
    Generic MCP agent system prompt for runtime tool integration.
   
    This prompt instructs the agent to:
    - Dynamically discover available MCP tools at runtime
    - Use tools efficiently when they help answer queries
    - Avoid assuming fixed toolsets
    - Minimize tool calls while maximizing effectiveness
    - Handle impossible requests gracefully
   
    Use this as the base system prompt for any MCP agent.
    """
    # Read the prompt content from external file
    prompt_file = Path(__file__).parent / "mcp_prompt.txt"
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "Error: mcp_prompt.txt file not found in prompts directory."
    except Exception as e:
        return f"Error reading prompt file: {str(e)}"