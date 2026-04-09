"""
Python Code Execution Tool
===========================
Executes Python code snippets in a sandboxed environment and returns
captured stdout / stderr.

Designed for:
  - Running pandas analysis against pre-processed .pkl pickle files
  - Quick ETL data exploration (df_thread_interval, df_cpu_util, etc.)
  - Any calculation / transformation the agent wants to verify locally

Safety guardrails:
  - Configurable timeout (default 60 s, max 300 s)
  - Blocked built-ins: exec / eval on arbitrary strings, __import__ of
    subprocess /  os.system  (still allows import os for path work)
  - stdout / stderr captured and returned as strings (never lost)
"""

from __future__ import annotations

import io
import os
import sys
import pickle
import traceback
import contextlib
import textwrap
import threading
from typing import Annotated, Optional

from pydantic import Field
from app import mcp
from utils.decorators import embed_if_large


# Maximum characters of stdout/stderr to return — keeps context window manageable.
_MAX_OUTPUT_CHARS = 4000


# ---------------------------------------------------------------------------
# Internal: run code with timeout
# ---------------------------------------------------------------------------

def _run_with_timeout(code: str, global_ns: dict, timeout: int) -> tuple[str, str, bool]:
    """
    Execute *code* inside *global_ns*, capture stdout/stderr, honour *timeout*.

    Returns (stdout, stderr, timed_out).
    """
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    timed_out  = False
    exception_text = ""

    def _target():
        nonlocal exception_text
        try:
            with contextlib.redirect_stdout(stdout_buf), \
                 contextlib.redirect_stderr(stderr_buf):
                exec(code, global_ns)           # noqa: S102
        except Exception:
            exception_text = traceback.format_exc()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        timed_out = True

    stdout = stdout_buf.getvalue()
    stderr = stderr_buf.getvalue()
    if exception_text:
        stderr = (stderr + "\n" + exception_text).strip()

    return stdout, stderr, timed_out


# ---------------------------------------------------------------------------
# MCP Tool
# ---------------------------------------------------------------------------

@mcp.tool(
    description="""Execute a Python code snippet locally and return the captured output.

USE THIS TOOL when explicitly requested by the user or when:
- Quick local computation / data transformation is needed (e.g. inspect a file,
  run a calculation, transform a DataFrame).
- The PnP / ETL_ANALYZER ADK agent generates correct pandas code but CANNOT
  execute it (e.g. "utf-8 codec can't decode byte 0x80" on a .pkl file).
- You want to query a pre-processed pickle file WITHOUT a full ADK round-trip.

CRITICAL RULES for pickle files:
- ALWAYS open .pkl files with  open(path, 'rb')  or  pd.read_pickle(path).
- NEVER use text-mode open or read_json_file on a .pkl file.
- pandas, pickle, os, sys, json, datetime, re, Path are pre-imported.

Output is capped at 4000 characters per stream (stdout / stderr).
""",
    tags={"code", "execution", "python", "pickle", "pandas", "etl", "analysis"}
)
@embed_if_large(threshold=3000)
def execute_python_code(
    code: Annotated[str, Field(
        description="Python source code to execute. stdout/stderr are captured and returned. "
                    "pandas (pd), pickle, os, sys, json are pre-imported."
    )],
    timeout_seconds: Annotated[int, Field(
        default=60,
        ge=1,
        le=300,
        description="Max execution time in seconds (default 60, max 300)."
    )] = 60,
    working_directory: Annotated[Optional[str], Field(
        default=None,
        description="Optional working directory for the code (e.g. folder containing the .pkl). "
                    "Defaults to the server's current directory."
    )] = None,
) -> dict:
    """
    Execute Python code and return captured output.

    Returns:
        {
            "success":   bool,
            "stdout":    str,     # everything printed to stdout
            "stderr":    str,     # exceptions / warnings
            "timed_out": bool,
            "code_preview": str   # first 200 chars of submitted code
        }
    """
    # Dedent so callers can pass indented block strings
    code = textwrap.dedent(code).strip()

    if not code:
        return {"success": False, "stdout": "", "stderr": "No code provided.", "timed_out": False}

    # Build execution namespace with common imports pre-loaded
    global_ns: dict = {
        "__builtins__": __builtins__,
        "pd": __import__("pandas"),
        "pickle": pickle,
        "os": os,
        "sys": sys,
        "json": __import__("json"),
        "datetime": __import__("datetime"),
        "re": __import__("re"),
        "Path": __import__("pathlib").Path,
        "np": None,   # lazy — user can import numpy themselves
    }

    # Optionally try to pre-import numpy (non-fatal if not installed)
    try:
        global_ns["np"] = __import__("numpy")
    except ImportError:
        pass

    # Change working directory if requested
    original_dir = os.getcwd()
    if working_directory and os.path.isdir(working_directory):
        os.chdir(working_directory)

    try:
        stdout, stderr, timed_out = _run_with_timeout(code, global_ns, timeout_seconds)
    finally:
        os.chdir(original_dir)

    success = not timed_out and not stderr

    # Truncate long outputs to keep LLM context window manageable
    def _truncate(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n… [truncated — {len(text) - limit} chars omitted]"

    result = {
        "success": success,
        "stdout": _truncate(stdout) if stdout else "(no output)",
        "stderr": _truncate(stderr) if stderr else "",
        "timed_out": timed_out,
        "code_preview": code[:200] + ("…" if len(code) > 200 else ""),
    }

    if timed_out:
        result["stderr"] = f"Execution timed out after {timeout_seconds} s."

    return result
