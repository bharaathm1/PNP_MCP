"""
Power Analysis Prompt — System prompt for the Power Analysis MCP server.

Provides the LLM with complete instructions for using all nine power tools:
  parse_power_config              — OPTIONAL: parse FlexLogger XML / PACS CSV config.
  analyze_power_summary           — PRIMARY (95 % of queries): summary file analysis.
  analyze_power_traces            — Time-series trace analysis over a time window.
  load_power_csv                  — Load CSV into per-session storage.
  load_power_json                 — Load JSON into per-session storage.
  analyze_power_dataframe         — LLM-driven pandas query on a loaded DataFrame.
  detect_power_rail_config        — Step 1 of comparison pipeline.
  process_summary_rails_to_json   — Step 2 of comparison pipeline.
  create_power_comparison_matrix  — Step 3 of comparison pipeline.
"""

from app import mcp
from pathlib import Path


@mcp.prompt(
    description=(
        "System prompt for the Power Analysis agent. "
        "Teaches the LLM the full workflow (config → summary → traces → comparison pipeline), "
        "all nine tool inputs/outputs, PACS vs FlexLogger format differences, "
        "fuzzy rail matching, and the three-step comparison pipeline. "
        "**USE THIS AS SYSTEM PROMPT** before any power analysis session."
    ),
    tags={
        "power", "agent", "system-prompt", "rail-analysis",
        "pacs", "flexlogger", "comparison", "pipeline",
    },
)
def power_analysis_prompt() -> str:
    """
    Power Analysis agent system prompt.

    Returns complete instructions for:
    - All 9 tools: inputs, outputs, when to use
    - Single-file quick-look workflow (analyze_power_summary first)
    - Three-step comparison pipeline for multi-run datasets
    - PACS vs FlexLogger format handling
    - Fuzzy rail matching rules
    - Worked examples
    - Common mistakes to avoid
    """
    prompt_file = Path(__file__).parent / "power_prompt.txt"
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Error: power_prompt.txt not found in prompts directory."
    except Exception as e:
        return f"Error reading power prompt file: {str(e)}"
