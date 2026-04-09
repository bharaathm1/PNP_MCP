"""
ETL Analysis Prompt - System prompt for the ETL Analysis MCP server.

Provides the LLM with complete instructions for using all nine ETL tools:
  discover_etl_files              - Find .etl files in a folder tree.
  check_analysis_pkl_exists       - Check for cached PKL files.
  list_standalone_scripts         - Catalogue or read standalone analysis scripts.
  create_custom_standalone_script - Generate a new custom script.
  run_standalone_script           - Run a script via speed.exe → PKL.
  load_dataframes_from_pickle     - Load PKL, return metadata + sample rows.
  analyze_trace_dataframe         - LLM-generates and runs pandas code on a DF.
  get_algorithm_documentation     - Read algorithm docs from local docs/.
  cleanup_pickle_files            - Remove old temp PKL files.
"""

from app import mcp
from pathlib import Path


@mcp.prompt(
    description=(
        "System prompt for the ETL Trace Analysis agent. "
        "Enforces three absolute rules: (1) df_trace_summary is ALWAYS the first "
        "and ONLY auto-run script for any summary/overview/analyze request; "
        "(2) comprehensive_analysis runs ONLY on explicit user request; "
        "(3) every other standalone script (wlc, ppm, containment, heteroresponse, etc.) "
        "is presented as a numbered menu — never auto-selected. "
        "Teaches the full 5-step flow: discover → cache-check → run df_trace_summary → "
        "execute_python_code Steps A–E → show menu and wait. "
        "**USE THIS AS SYSTEM PROMPT** before any ETL analysis session."
    ),
    tags={
        "etl", "agent", "system-prompt", "trace-analysis",
        "power", "performance", "ppm", "wlc", "containment",
    },
)
def etl_analysis_prompt() -> str:
    """
    ETL Analysis agent system prompt.

    Returns complete instructions for:
    - All 9 tools: inputs, outputs, when to use
    - Full decision tree (discover → cache → run → load → query)
    - Standalone script catalogue
    - DataFrame selection guide
    - Common mistakes to avoid
    """
    prompt_file = Path(__file__).parent / "etl_prompt.txt"
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Error: etl_prompt.txt not found in prompts directory."
    except Exception as e:
        return f"Error reading ETL prompt file: {str(e)}"
