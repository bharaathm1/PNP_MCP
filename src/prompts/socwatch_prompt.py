"""
SocWatch Analysis Prompt - System prompt for the SocWatch MCP server.

Provides the LLM with complete instructions for using the two SocWatch tools:
  find_socwatch_files  - Discover SocWatch CSV files in a folder tree.
  parse_socwatch_data  - Parse the discovered files → Excel + Markdown summary.
"""

from app import mcp
from pathlib import Path


@mcp.prompt(
    description=(
        "System prompt for the SocWatch Analysis agent. "
        "Teaches the LLM the two-phase workflow (discovery → parse), "
        "tool inputs/outputs, decision tree, and common mistakes. "
        "**USE THIS AS SYSTEM PROMPT** before any SocWatch analysis session."
    ),
    tags={"socwatch", "agent", "system-prompt", "power-analysis", "c-state", "p-state"}
)
def socwatch_analysis_prompt() -> str:
    """
    SocWatch Analysis agent system prompt.

    Returns complete instructions for:
    - find_socwatch_files: folder discovery, hybrid detection, return values
    - parse_socwatch_data: parsing all 21 sections, output artifacts
    - Full decision tree and worked examples
    - Common mistakes to avoid
    """
    prompt_file = Path(__file__).parent / "socwatch_prompt.txt"
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Error: socwatch_prompt.txt not found in prompts directory."
    except Exception as e:
        return f"Error reading SocWatch prompt file: {str(e)}"
