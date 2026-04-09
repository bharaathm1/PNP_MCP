#!/usr/bin/env python3
"""
Power + SocWatch MCP Server — stdio transport for local VS Code use.

VS Code spawns this process automatically via .vscode/mcp.json.
No server to start manually. No port. No URL.

Tools exposed:
  Power (9):
    parse_power_config             — Parse config file (XML/CSV/pickle) for rail mappings
    analyze_power_summary          — Primary analysis tool (95% of queries)
    analyze_power_traces           — Time-series trace analysis for a time window
    load_power_csv                 — Load arbitrary CSV into session storage
    load_power_json                — Load arbitrary JSON into session storage
    analyze_power_dataframe        — LLM-driven pandas query on a loaded DataFrame
    detect_power_rail_config       — Generate PowerRailConfig.txt from folder (Step 1)
    process_summary_rails_to_json  — Extract target rails from summaries → JSON (Step 2)
    create_power_comparison_matrix — Build cross-run comparison Excel/CSV/Markdown (Step 3)

  SocWatch (2):
    find_socwatch_files            — Discover + copy SocWatch CSVs from result folder tree
    parse_socwatch_data            — Parse CSVs → Excel + Markdown summary

  Knowledge (2):
    load_power_rail_knowledge_to_mongodb — Seed KB once at session start
    search_power_rail_knowledge          — Lookup rail descriptions + debug hints

Prompts:
  power_socwatch_analysis_prompt  — Unified 3-phase workflow system prompt

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

from tools import power_tools                # noqa: F401, E402
from tools import socwatch_tools             # noqa: F401, E402
from tools import power_rail_knowledge_tools # noqa: F401, E402
from prompts import power_socwatch_prompt    # noqa: F401, E402

# ---------------------------------------------------------------------------
# stdout guard — MUST come before mcp.run()
# In stdio transport, stdout is the JSON-RPC wire. Any accidental print()
# anywhere in the process (tools, logging, third-party libs) will corrupt
# the protocol framing and cause VS Code to drop all tool registrations.
# This guard redirects the real stdout to stderr so stray writes are
# visible in the VS Code Output panel but never reach the transport.
# ---------------------------------------------------------------------------
class _StderrProxy:
    """Proxy that forwards all writes to stderr instead of stdout."""
    def write(self, data):
        sys.stderr.write(data)
    def flush(self):
        sys.stderr.flush()
    def fileno(self):
        return sys.stderr.fileno()
    @property
    def encoding(self):
        return sys.stderr.encoding
    @property
    def errors(self):
        return sys.stderr.errors
    def isatty(self):
        return False

_real_stdout = sys.stdout  # FastMCP will replace this with its transport writer
# We do NOT redirect sys.stdout here — FastMCP owns it for stdio transport.
# The fixes are at the source: logger.py uses stderr, safe_print uses stderr.

# ---------------------------------------------------------------------------
# Entry point — stdio transport (VS Code owns this process)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.mcp.run(transport="stdio", show_banner=False)  # banner corrupts JSON-RPC framing
