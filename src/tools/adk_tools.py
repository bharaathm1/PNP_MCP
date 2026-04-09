"""
ADK Tools - MCP tools for querying AutoBots ADK agents
"""

from typing import Annotated, Optional
from pydantic import Field

from fastmcp import Context
from app import mcp
from .adk_session_manager import get_session_manager


@mcp.tool(
    description="""Query an AutoBots ADK agent with persistent session conversation context.

Available agents:
- 'PnP'                       — ETL trace files (.etl / .pkl): CPU utilization, PPM settings, process/thread stats
- 'PowerSocwatchDataCompiler' — Power files (PACS/FlexLogger) + SocWatch CSV files: power rail analysis, Excel compilation

Session Persistence:
- The MCP session_id is auto-managed — you do NOT need to pass session_id unless you want a named sub-session.
- Using the same effective session_id keeps the agent's full conversation memory (files loaded, results, context).
- To start fresh, call reset_adk_session or the user must explicitly ask.

File Discovery:
- If the user asks to list files, find ETL files, or discover what’s in a folder — call THIS tool directly.
  Do NOT ask the user to run terminal commands or provide file lists manually.
  The PnP agent can enumerate files on the local system.

Examples:
- User: “List ETL files in E:\\agents” → query_adk_agent(agent_name='PnP', query='List all .etl files under E:\\agents recursively')
- User: “Analyse E:\\agents\\run1.etl”   → query_adk_agent(agent_name='PnP', query='Analyse E:\\agents\\run1.etl ...')
- Follow-up: “Show PPM settings”         → query_adk_agent(agent_name='PnP', query='Show PPM settings')  # same session, agent remembers""",
    tags={"adk", "autobots", "agent", "pnp", "power", "socwatch", "etl"}
)
async def query_adk_agent(
    agent_name: Annotated[str, Field(
        description="Agent to use: 'PnP' (ETL files) or 'PowerSocwatchDataCompiler' (power/SocWatch files)."
    )],
    query: Annotated[str, Field(
        description="Natural language query for the agent."
    )],
    ctx: Context,
    session_id: Annotated[Optional[str], Field(
        default=None,
        description="Optional named sub-session. If omitted, the MCP connection session_id is used automatically — each new chat gets a fresh session."
    )] = None,
) -> dict:
    """
    Query AutoBots ADK agent with session persistence.

    Uses the MCP connection’s session_id by default, ensuring each new client
    connection (new chat) starts with a clean ADK session automatically.
    """
    # Derive session: explicit override → MCP session_id → fallback
    effective_session = session_id or ctx.session_id or "default"

    manager = get_session_manager()
    result = await manager.query_agent(
        agent_name=agent_name,
        session_id=effective_session,
        query=query
    )
    return result


@mcp.tool(
    description="Reset ADK agent session — clears conversation history and dataframe state. Use when the user explicitly asks to start fresh.",
    tags={"adk", "session", "reset"}
)
async def reset_adk_session(
    agent_name: Annotated[str, Field(
        description="Agent name: 'PnP' or 'PowerSocwatchDataCompiler'"
    )],
    ctx: Context,
    session_id: Annotated[Optional[str], Field(
        default=None,
        description="Session to reset. If omitted, resets the current MCP connection session."
    )] = None,
) -> dict:
    """
    Reset/clear an ADK agent session.
    Deletes both session file and state file.
    """
    import os

    effective_session = session_id or ctx.session_id or "default"
    manager = get_session_manager()
    session_file = manager._get_session_file_path(agent_name, effective_session)
    state_file = manager._get_state_file_path(agent_name, effective_session)
    
    success = True
    messages = []
    
    for file, name in [(session_file, "session"), (state_file, "state")]:
        if file.exists():
            try:
                os.remove(file)
                messages.append(f"{name} deleted")
            except Exception as e:
                success = False
                messages.append(f"{name} delete failed: {e}")
    
    return {
        "success": success,
        "message": "; ".join(messages) if messages else "No files found"
    }
