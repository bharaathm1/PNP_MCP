"""
Power + SocWatch Combined Prompt — System prompt for the combined Power + SocWatch MCP server.

Registers: power_socwatch_analysis_prompt
"""

from app import mcp
from pathlib import Path


@mcp.prompt(
    description=(
        "System prompt for the combined Power + SocWatch Analysis agent. "
        "Teaches the LLM the unified 3-phase workflow: "
        "(1) parallel discovery of power *_summary.csv files AND SocWatch CSV files, "
        "(2) parallel compilation via compile_power_data + parse_socwatch_data, "
        "(3) cross-referenced query and unified interpretation table linking "
        "power rail values to hardware telemetry evidence from SocWatch. "
        "**USE THIS AS SYSTEM PROMPT** before any combined power+SocWatch analysis session."
    ),
    tags={
        "power", "socwatch", "combined", "agent", "system-prompt",
        "rail-analysis", "cstate", "pstate", "intel", "platform",
    },
)
def power_socwatch_analysis_prompt() -> str:
    """
    Power + SocWatch combined agent system prompt.

    Returns complete instructions for:
    - All 6 tools (3 power + 3 SocWatch) + 2 KB tools
    - Parallel discovery and compile phases
    - Cross-referenced unified interpretation table (power mW + SocWatch telemetry)
    - Graceful degradation when only one dataset is present
    - Worked examples (both datasets, power-only, cache hit)
    - Common mistakes to avoid
    """
    prompt_file = Path(__file__).parent / "power_socwatch_prompt.txt"
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Error: power_socwatch_prompt.txt not found in prompts directory."
    except Exception as e:
        return f"Error reading power_socwatch prompt file: {str(e)}"
