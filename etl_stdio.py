#!/usr/bin/env python3
"""
ETL Analysis MCP Server — stdio transport for local VS Code use.

VS Code spawns this process automatically via .vscode/mcp.json.
No server to start manually. No port. No URL.

Tools exposed:
  discover_etl_files              — Find .etl files in a folder tree
  check_analysis_pkl_exists       — Check for cached PKL files
  list_standalone_scripts         — List/read analysis scripts
  create_custom_standalone_script — Generate a new custom script
  run_standalone_script           — Run script via speed.exe → PKL
  load_dataframes_from_pickle     — Load PKL, return metadata + sample rows
  get_algorithm_documentation     — Read algorithm docs
  cleanup_pickle_files            — Remove old temp PKL files
  execute_python_code             — Run LLM-generated pandas code

Prompt:
  etl_analysis_prompt             — Full workflow system prompt

Setup:
  1. pip install -r requirements.txt
  2. Copy .vscode/mcp-config-template.json → .vscode/mcp.json
  3. Reload VS Code window
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — tools live in the sibling fastmcp-server-template/src/
# ---------------------------------------------------------------------------
THIS_DIR = Path(__file__).parent.resolve()
SRC_DIR  = (THIS_DIR / "src").resolve()

if not SRC_DIR.exists():
    raise RuntimeError(
        f"Cannot find src/ at {SRC_DIR}\n"
        "Run setup.bat first to create the virtual environment and install dependencies,\n"
        "then open this folder in VS Code."
    )

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(THIS_DIR))  # for config package

# ---------------------------------------------------------------------------
# Bootstrap app + register tools + prompt
# ---------------------------------------------------------------------------
import app  # noqa: E402  creates the global FastMCP instance

from tools import etl_tools            # noqa: F401, E402  registers ETL tools
from tools import etl_knowledge_tools  # noqa: F401, E402  registers ETL knowledge search
from tools import code_execution_tools # noqa: F401, E402  registers execute_python_code
from prompts import etl_prompt         # noqa: F401, E402  registers etl_analysis_prompt

# ---------------------------------------------------------------------------
# Entry point — stdio transport (VS Code owns this process)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.mcp.run(transport="stdio", show_banner=False)  # banner corrupts JSON-RPC framing
