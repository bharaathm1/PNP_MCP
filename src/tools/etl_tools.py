"""
ETL Analysis Tools - MCP tools for parsing and querying Intel ETL trace files.

Eight entry-point MCP tools:
  discover_etl_files              - Find .etl files in a folder tree.
  check_analysis_pkl_exists       - Check for cached PKL files for an ETL.
  list_standalone_scripts         - Catalogue or read source of standalone scripts.
  create_custom_standalone_script - Generate a new custom analysis script.
  run_standalone_script           - Run a targeted standalone script via speed.exe → PKL.
  load_dataframes_from_pickle     - Load PKL and return DF metadata + sample rows.
  get_algorithm_documentation     - Read algorithm docs from local docs/algorithms/.
  cleanup_pickle_files            - Remove old temp ETL PKL files.
  pregen_analysis_pkls            - Pre-generate PKLs for all ETLs in a folder in parallel.
  list_available_analysis         - Show all ready PKLs across a folder tree.

DataFrame analysis workflow:
  1. run_standalone_script / check_analysis_pkl_exists  → get PKL path
  2. load_dataframes_from_pickle                        → LLM sees schema + sample rows
  3. LLM (frontend) writes pandas code using that schema
  4. execute_python_code (code_execution_tools)         → runs the generated code

All heavy ETL parsing goes through speed.exe (via speedlibs_service_client.py),
which is copied into the local etl_standalone/ folder — no dependency on the
original ETL_ANALYZER agent folder.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd

from app import mcp
from utils.decorators import embed_if_large, async_tool

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).parent
ETL_STANDALONE_DIR = _THIS_DIR / "etl_standalone"
ETL_DOCS_DIR = ETL_STANDALONE_DIR / "docs" / "algorithms"

# Add standalone dir to path so speedlibs_service_client is importable
if str(ETL_STANDALONE_DIR) not in sys.path:
    sys.path.insert(0, str(ETL_STANDALONE_DIR))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Targeted PKL suffixes (deterministic filenames produced by standalone scripts)
# ---------------------------------------------------------------------------
_TARGETED_PKL_SUFFIXES = [
    # Quick-start starters (checked by agent before running anything)
    "df_trace_summary",
    "df_threadstat",
    "df_processlifetime",
    # Grouped targeted scripts
    "containment",
    "ppm",
    "heteroresponse",
    "cpu_freq_util",
    "power_state",
    "wlc",
    "process_stats",
]

# ---------------------------------------------------------------------------
# DataFrame domain context (used to enrich load_dataframes_from_pickle output
# so the frontend LLM has enough context to write correct pandas code)
# ---------------------------------------------------------------------------
_DF_CONTEXTS: Dict[str, Dict] = {
    "summary_processstats_df": {
        "description": "Process-level performance statistics — CPU time, concurrency, QoS",
        "common_queries": [
            "Show top 10 processes by CPU time",
            "Find processes with >5% CPU",
            "Show processes with QoS violations",
        ],
    },
    "summary_utilizationperlogical_df": {
        "description": "Per-logical-CPU utilization aggregated — avg/peak usage",
        "common_queries": [
            "Show average utilization per core",
            "Which cores exceeded 80%?",
            "Compare P-core vs E-core utilization",
        ],
    },
    "summary_cpufrequencystats_df": {
        "description": "Per-CPU frequency statistics — min/max/avg frequencies",
        "common_queries": [
            "Show average frequency per core",
            "Find cores with throttling",
            "Compare P-core vs E-core frequency range",
        ],
    },
    "summary_qosperprocess_df": {
        "description": "QoS metrics per process — application-level service guarantees",
        "common_queries": ["Show QoS violations by process", "Find high-priority processes"],
    },
    "summary_qospercore_df": {
        "description": "QoS metrics per CPU core",
        "common_queries": ["QoS compliance per core", "Find cores with violations"],
    },
    "df_containment_breach": {
        "description": "Containment policy breach events — workload exceeded E-core capacity",
        "common_queries": [
            "Show all breach events",
            "Find longest breaches",
            "Breach trigger reasons",
        ],
    },
    "df_PPM_behaviour": {
        "description": "PPM constraint validation results — per-setting compliance",
        "common_queries": ["Show PPM violations", "Which constraints failed?"],
    },
    "df_heteroresponse": {
        "description": "Heterogeneous scheduling — estimated vs actual utility",
        "common_queries": ["Show scheduling decisions", "Find mispredictions"],
    },
    "df_wlc": {
        "description": "Workload Classification — SOCWC events per process",
        "common_queries": ["Show classification per process", "Find WLC transitions"],
    },
    "df_cpu_util": {
        "description": "Per-CPU core utilization timeseries",
        "common_queries": [
            "Show utilization trend for CPU 0",
            "Find peaks above 90%",
        ],
    },
    "df_cpu_freq": {
        "description": "Per-CPU core frequency in GHz timeseries",
        "common_queries": ["Show frequency trend", "Find throttling periods"],
    },
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe(obj: Any) -> str:
    """Convert anything to an ASCII-safe string."""
    try:
        return str(obj)
    except Exception:
        return str(obj).encode("ascii", "replace").decode("ascii")


def _load_pkl(pkl_path: str) -> Dict[str, Any]:
    """Load a pickle file and return its contents dict."""
    with open(pkl_path, "rb") as fh:
        data = pickle.load(fh)
    return data if isinstance(data, dict) else {"data": data}


def _df_summary(data: Dict[str, Any], max_sample_rows: int = 50) -> Dict[str, Any]:
    """
    For every DataFrame in *data* return shape, columns, dtype, sample rows,
    and basic numeric stats so the LLM can answer questions without extra tool calls.
    """
    summary: Dict[str, Any] = {}
    for key, obj in data.items():
        if not (hasattr(obj, "shape") and hasattr(obj, "columns")):
            summary[key] = {"type": type(obj).__name__, "is_dataframe": False}
            continue
        df: pd.DataFrame = obj
        col_info = []
        for col in df.columns:
            info: Dict[str, Any] = {
                "name": _safe(col),
                "dtype": str(df[col].dtype),
                "nulls": int(df[col].isnull().sum()),
                "unique": int(df[col].nunique()),
                "sample": [_safe(v) for v in df[col].dropna().head(3).tolist()],
            }
            if pd.api.types.is_numeric_dtype(df[col]):
                info["stats"] = {
                    "min": float(df[col].min()) if not df[col].empty else None,
                    "max": float(df[col].max()) if not df[col].empty else None,
                    "mean": float(df[col].mean()) if not df[col].empty else None,
                }
            col_info.append(info)
        summary[key] = {
            "is_dataframe": True,
            "shape": {"rows": int(df.shape[0]), "cols": int(df.shape[1])},
            "columns": col_info,
            "sample_rows": df.head(max_sample_rows).to_dict(orient="records"),
            "context": _DF_CONTEXTS.get(key, {}).get("description", ""),
            "common_queries": _DF_CONTEXTS.get(key, {}).get("common_queries", []),
        }
    return summary


# ---------------------------------------------------------------------------
# PKL info helper
# ---------------------------------------------------------------------------

def _pkl_info(path: Optional[str]) -> Optional[Dict]:
    if not path or not os.path.exists(path):
        return None
    try:
        st = os.stat(path)
        return {
            "path": path,
            "size_mb": round(st.st_size / 1024 / 1024, 2),
            "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
    except OSError:
        return {"path": path, "size_mb": None, "modified": None}


# ===========================================================================
# MCP TOOLS
# ===========================================================================

@mcp.tool()
@async_tool
@embed_if_large(threshold=7000)
def discover_etl_files(directory_path: str) -> Dict[str, Any]:
    """
    Discover all .etl trace files in a directory and its sub-directories.

    Args:
        directory_path: Root folder to search.

    Returns:
        etl_files: list of {path, name, size_mb, size_gb, directory}
        total_count, total_size_gb, largest_file, message
    """
    try:
        if not os.path.exists(directory_path):
            return {"success": False, "error": f"Directory not found: {directory_path}"}

        etl_files = []
        for root, _dirs, files in os.walk(directory_path):
            for f in files:
                if f.lower().endswith(".etl"):
                    fp = os.path.join(root, f)
                    sz = os.path.getsize(fp)
                    etl_files.append({
                        "path": fp,
                        "name": f,
                        "size_mb": round(sz / 1024 / 1024, 2),
                        "size_gb": round(sz / 1024 / 1024 / 1024, 3),
                        "directory": root,
                    })

        etl_files.sort(key=lambda x: x["size_mb"], reverse=True)
        total_gb = round(sum(f["size_mb"] for f in etl_files) / 1024, 2)
        return {
            "success": True,
            "etl_files": etl_files,
            "total_count": len(etl_files),
            "total_size_gb": total_gb,
            "largest_file": etl_files[0] if etl_files else None,
            "message": f"Found {len(etl_files)} ETL file(s) totalling {total_gb} GB",
        }
    except Exception as exc:
        return {"success": False, "error": _safe(exc)}


@mcp.tool()
@async_tool
@embed_if_large(threshold=7000)
def check_analysis_pkl_exists(etl_file_path: str) -> Dict[str, Any]:
    """
    Check whether cached PKL files already exist for a given ETL file.

    Looks in the same directory as the ETL for:
      - Comprehensive PKLs  : <etl_basename>_<timestamp>_dfs.pkl
      - Teams KPI PKLs      : <etl_basename>_<timestamp>_teams_kpi.pkl
      - Targeted PKLs       : <etl_basename>_<suffix>.pkl  (e.g. _containment.pkl)

    Args:
        etl_file_path: Full path to the ETL file.

    Returns:
        comprehensive_available  — True if a comprehensive PKL exists (superset of all DFs)
        comprehensive_pkl        — path to the comprehensive PKL, or null
        trace_summary_available  — True if a df_trace_summary PKL exists specifically
        trace_summary_pkl        — path to the df_trace_summary PKL, or null
        teams_available          — True if a Teams KPI PKL exists
        teams_pkl                — path to the Teams KPI PKL, or null
        targeted_pkls            — dict {suffix: path} for all OTHER targeted PKLs found
                                   (wlc, ppm, containment, etc.) — NOT for deciding
                                   what to load for a summary request
        any_available            — True if ANY pkl exists; do NOT use this alone to
                                   select which pkl to load for a summary request
        all_found_pkls, message
    """
    try:
        if not etl_file_path:
            return {"success": False, "error": "etl_file_path is required", "any_available": False}

        etl_dir = os.path.dirname(os.path.abspath(etl_file_path))
        base = os.path.splitext(os.path.basename(etl_file_path))[0]

        comp_files = glob.glob(os.path.join(etl_dir, f"{base}_*_dfs.pkl"))
        comp_pkl = max(comp_files, key=os.path.getmtime) if comp_files else None

        teams_files = glob.glob(os.path.join(etl_dir, f"{base}_*_teams_kpi.pkl"))
        teams_pkl = max(teams_files, key=os.path.getmtime) if teams_files else None

        def _valid_pkl(p: str) -> bool:
            """Return False for missing or corrupt (< 10 KB) PKLs."""
            try:
                return p is not None and os.path.exists(p) and os.path.getsize(p) >= 10240
            except OSError:
                return False

        targeted: Dict[str, str] = {}
        for suffix in _TARGETED_PKL_SUFFIXES:
            p = os.path.join(etl_dir, f"{base}_{suffix}.pkl")
            if _valid_pkl(p):
                targeted[suffix] = p

        all_found = sorted(
            set(comp_files + teams_files + list(targeted.values())),
            key=os.path.getmtime, reverse=True
        )

        comp_ok  = _valid_pkl(comp_pkl)
        teams_ok = _valid_pkl(teams_pkl)
        any_ok   = comp_ok or teams_ok or bool(targeted)

        # Explicit top-level field for df_trace_summary so agents never have
        # to dig through targeted_pkls to find it.
        trace_summary_pkl = targeted.get("df_trace_summary")
        trace_summary_available = _valid_pkl(trace_summary_pkl)

        parts = []
        if comp_ok:
            parts.append(f"comprehensive PKL: {comp_pkl}")
        if teams_ok:
            parts.append(f"Teams KPI PKL: {teams_pkl}")
        if targeted:
            parts.append(f"targeted PKLs: {', '.join(targeted)}"
        )
        if not any_ok:
            parts.append(f"no PKL found for '{base}' in {etl_dir}")

        return {
            "success": True,
            "etl_file_path": etl_file_path,
            "etl_basename": base,
            "etl_directory": etl_dir,
            "comprehensive_available": comp_ok,
            "comprehensive_pkl": comp_pkl,
            "comprehensive_pkl_info": _pkl_info(comp_pkl),
            "teams_available": teams_ok,
            "teams_pkl": teams_pkl,
            "teams_pkl_info": _pkl_info(teams_pkl),
            "trace_summary_available": trace_summary_available,
            "trace_summary_pkl": trace_summary_pkl,
            "targeted_pkls": targeted,
            "targeted_available": list(targeted.keys()),
            "any_available": any_ok,
            "all_found_pkls": all_found,
            "message": "; ".join(parts),
        }
    except Exception as exc:
        return {"success": False, "error": _safe(exc), "any_available": False}


@mcp.tool()
@async_tool
@embed_if_large(threshold=7000)
def list_standalone_scripts(script_name: str = None) -> Dict[str, Any]:
    """
    List all standalone analysis scripts in the local etl_standalone/ folder,
    or return the full source code of a specific script.

    Args:
        script_name: Optional — filename (e.g. 'standalone_df_wlc.py') or bare
                     suffix (e.g. 'df_wlc'). When given, returns full source code.
                     When omitted, returns the full catalogue.

    Returns:
        Without script_name: scripts (list), total, mcp_directory
        With script_name   : script_name, script_path, source_code, docstring
    """
    scripts_dir = ETL_STANDALONE_DIR

    if script_name:
        if not script_name.endswith(".py"):
            script_name = f"standalone_{script_name}.py"
        sp = scripts_dir / script_name
        if not sp.exists():
            cands = [p for p in scripts_dir.glob("standalone_*.py")
                     if p.name.lower() == script_name.lower()]
            if cands:
                sp = cands[0]
                script_name = sp.name
            else:
                return {
                    "success": False,
                    "error": f"Script '{script_name}' not found. "
                             "Call list_standalone_scripts() with no args to see all.",
                }
        source = sp.read_text(encoding="utf-8")
        # Extract first docstring
        docstring, in_doc, lines_buf = "", False, []
        for ln in source.splitlines():
            s = ln.strip()
            if not in_doc and s.startswith('"""'):
                in_doc = True
                rest = s[3:]
                if rest.endswith('"""') and len(rest) > 3:
                    docstring = rest[:-3].strip()
                    break
                lines_buf.append(rest)
                continue
            if in_doc:
                if '"""' in s:
                    lines_buf.append(s[:s.index('"""')])
                    break
                lines_buf.append(ln)
        if not docstring:
            docstring = "\n".join(lines_buf).strip()
        return {
            "success": True,
            "script_name": script_name,
            "script_path": str(sp),
            "source_code": source,
            "docstring": docstring,
        }

    scripts = []
    for sp in sorted(scripts_dir.glob("standalone_*.py")):
        entry = {
            "script": sp.name,
            "script_path": str(sp),
            "pkl_suffix": sp.stem.replace("standalone_", ""),
            "docstring_summary": "",
        }
        try:
            text = sp.read_text(encoding="utf-8", errors="ignore")
            in_doc, buf = False, []
            for ln in text.splitlines():
                s = ln.strip()
                if not in_doc and s.startswith('"""'):
                    in_doc = True
                    rest = s[3:]
                    if rest.endswith('"""') and len(rest) > 3:
                        entry["docstring_summary"] = rest[:-3].strip()
                        break
                    if rest:
                        buf.append(rest)
                    continue
                if in_doc:
                    if '"""' in s:
                        buf.append(s[:s.index('"""')])
                        break
                    buf.append(s)
            if not entry["docstring_summary"]:
                for dl in "\n".join(buf).splitlines():
                    if dl.strip():
                        entry["docstring_summary"] = dl.strip()
                        break
        except Exception:
            pass
        scripts.append(entry)

    return {
        "success": True,
        "total": len(scripts),
        "scripts": scripts,
        "mcp_directory": str(scripts_dir),
        "usage_hint": (
            "Pass script_name='df_wlc' to read full source. "
            "Call run_standalone_script(etl_path, 'df_wlc') to execute. "
            "Call create_custom_standalone_script() to generate a new script."
        ),
    }


@mcp.tool()
@async_tool
@embed_if_large(threshold=7000)
def create_custom_standalone_script(
    script_name: str,
    output_key: str,
    description: str,
    analysis_logic: str,
) -> Dict[str, Any]:
    """
    Generate a new standalone analysis script from a template and save it in
    the local etl_standalone/ folder.  Only the analysis_logic body is needed —
    the boilerplate (SPEED kernel setup, PKL cache check, PKL save, main) is
    written automatically.

    Args:
        script_name:    Short name, e.g. 'my_metric'. File: standalone_my_metric.py
        output_key:     Primary dict key for the PKL output, e.g. 'df_my_metric'.
                        The analysis_logic MUST assign this variable as a pd.DataFrame.
        description:    One-paragraph description placed in the module docstring.
        analysis_logic: Python body that runs inside the trace-loaded context.
                        Receives: trace (loaded ETL), etl_file_path (str).
                        MUST produce a pd.DataFrame named exactly `output_key`.

                        SPEED API — use ONLY these patterns to read events:

                        # All events (generic):
                        for ev in trace.get_events():
                            ev["TimeStamp"], ev["EventName"], ev["ProcessId"] ...

                        # Filtered by provider+event (preferred for ETW events):
                        evts = trace.get_events(
                            event_types=["Provider/EventName/win:Info"])

                        # Filtered by provider name only:
                        evts = trace.get_events(
                            event_types=["Microsoft-Windows-Kernel-Processor-Power"])

                        DO NOT import or use: speed.explorer, ev.filter_provider,
                        tracedm.events, or any other invented module path.
                        pandas and numpy are already imported at the top level.

    Returns:
        script_path, script_name, pkl_suffix, preview (first 30 lines)
    """
    import textwrap as _textwrap

    script_name = script_name.strip().replace(" ", "_")
    if script_name.startswith("standalone_"):
        script_name = script_name[len("standalone_"):]
    if script_name.endswith(".py"):
        script_name = script_name[:-3]

    filename = f"standalone_{script_name}.py"
    pkl_suffix = script_name
    script_path = ETL_STANDALONE_DIR / filename

    indented = _textwrap.indent(_textwrap.dedent(analysis_logic), "    ")

    content = f'''\
"""
Custom Standalone: {script_name}
{'=' * (len(script_name) + 21)}
{description}

PKL: <etl_basename>_{pkl_suffix}.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.
"""
import sys, os, argparse, pickle
from datetime import datetime

import pandas as pd
import numpy as np
if not hasattr(np, "int"):
    np.int = int; np.float = float; np.complex = complex; np.bool = bool

try:
    import tracedm
    print("[OK] SPEED kernel loaded")
except ImportError as e:
    print(f"[ERROR] {{e}}"); sys.exit(1)

PKL_SUFFIX = "{pkl_suffix}"


def _pkl_path(etl: str) -> str:
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{{b}}_{{PKL_SUFFIX}}.pkl")


def run_analysis(trace, etl_file_path: str) -> dict:
    """User-provided analysis logic."""
    # SPEED event API:
    #   trace.get_events()                          — all events
    #   trace.get_events(event_types=["Prov/Evt"])  — filtered
    # Each item: ev["TimeStamp"], ev["EventName"], ev["ProcessId"], ev["<field>"]
    # Do NOT use speed.explorer or any other invented import.
{indented}
    return {{"{output_key}": {output_key}}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etl_file", required=True)
    args = ap.parse_args()
    if not os.path.exists(args.etl_file):
        print(f"[ERROR] Not found: {{args.etl_file}}"); sys.exit(1)
    pkl = _pkl_path(args.etl_file)
    if os.path.exists(pkl):
        print(f"[CACHE HIT] {{pkl}}"); print(f"[OUTPUT_PKL] {{pkl}}"); sys.exit(0)
    trace = tracedm.load_trace(etl_file=args.etl_file)
    data = run_analysis(trace, args.etl_file)
    data["meta"] = {{"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                     "timestamp": datetime.now().isoformat()}}
    with open(pkl, "wb") as f:
        pickle.dump(data, f)
    print(f"[OK] {{pkl}}"); print(f"[OUTPUT_PKL] {{pkl}}")


if __name__ == "__main__":
    main()
'''

    try:
        script_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        return {"success": False, "error": f"Failed to write script: {exc}"}

    return {
        "success": True,
        "script_name": filename,
        "script_path": str(script_path),
        "pkl_suffix": pkl_suffix,
        "output_key": output_key,
        "preview": "\n".join(content.splitlines()[:30]),
        "usage_hint": f"Run via: run_standalone_script(etl_path, '{script_name}')",
    }


@mcp.tool()
@async_tool
@embed_if_large(threshold=7000)
def run_standalone_script(etl_file_path: str, script_name: str) -> Dict[str, Any]:
    """
    Run a targeted standalone analysis script via speed.exe for a specific ETL file.

    The script will:
      1. Check if the PKL already exists (cache hit) — returns immediately.
      2. Load the ETL trace inside the speed.exe SPEED kernel.
      3. Extract only the data relevant to that analysis.
      4. Save a PKL file next to the ETL file.

    PKL naming:
      - Targeted : <etl_basename>_<suffix>.pkl   (deterministic, no timestamp)

    Args:
        etl_file_path: Full path to the ETL file.
        script_name:   Filename or bare suffix, e.g. 'standalone_containment.py',
                       'containment', 'ppm', 'wlc', 'df_wlc', etc.

    Returns:
        pkl_file_path, cache_hit, processing_time, dataframe_keys, message
    """
    # Aliases — common misspellings/variants → canonical script names
    _SCRIPT_ALIASES = {
        "trace_summary":    "df_trace_summary",
        "tracesummary":     "df_trace_summary",
        "summary":          "df_trace_summary",
        "df_wlc":           "wlc",
        "df_ppm":           "ppm",
        "df_containment":   "containment",
    }
    _bare = script_name.lower()
    if _bare.endswith(".py"):
        _bare = _bare[:-3]
    script_name = _SCRIPT_ALIASES.get(_bare, script_name)

    try:
        if not etl_file_path or not os.path.exists(etl_file_path):
            return {"success": False, "error": f"ETL file not found: {etl_file_path}"}

        # Resolve script name
        if not script_name.endswith(".py"):
            script_name = f"standalone_{script_name}.py"
        sp = ETL_STANDALONE_DIR / script_name
        if not sp.exists():
            return {
                "success": False,
                "error": f"Script not found: {sp}. "
                         "Call list_standalone_scripts() to see available scripts.",
            }

        etl_dir = os.path.dirname(os.path.abspath(etl_file_path))
        etl_base = os.path.splitext(os.path.basename(etl_file_path))[0]
        suffix = sp.stem.replace("standalone_", "")
        expected_pkl = os.path.join(etl_dir, f"{etl_base}_{suffix}.pkl")

        # Cache check — comprehensive uses a timestamped name, check via glob
        if suffix == "comprehensive_analysis":
            comp_files = glob.glob(os.path.join(etl_dir, f"{etl_base}_*_dfs.pkl"))
            if comp_files:
                cached = max(comp_files, key=os.path.getmtime)
                try:
                    keys = list(_load_pkl(cached).keys())
                except Exception:
                    keys = []
                return {
                    "success": True,
                    "cache_hit": True,
                    "pkl_file_path": cached,
                    "processing_time": 0,
                    "dataframe_keys": keys,
                    "message": f"Cache hit — comprehensive PKL already exists: {cached}",
                }

        if os.path.exists(expected_pkl):
            try:
                keys = list(_load_pkl(expected_pkl).keys())
            except Exception:
                keys = []
            return {
                "success": True,
                "cache_hit": True,
                "pkl_file_path": expected_pkl,
                "processing_time": 0,
                "dataframe_keys": keys,
                "message": f"Cache hit — PKL already exists: {expected_pkl}",
            }

        # Get speed.exe from the local speedlibs_service_client
        try:
            import speedlibs_service_client as _ssc  # noqa: PLC0415
            speed_exe = _ssc._standalone_client.speed_exe_path
        except Exception as exc:
            return {"success": False, "error": f"Cannot locate speed.exe: {exc}"}

        if not os.path.exists(speed_exe):
            return {"success": False, "error": f"speed.exe not found at: {speed_exe}"}

        cmd = [speed_exe, "run", str(sp), "--etl_file", etl_file_path]
        t0 = time.time()
        returncode, stdout_text, stderr_text = _ssc._standalone_client._run_speed_exe(
            cmd, _ssc._standalone_client.timeout_analyze
        )
        elapsed = round(time.time() - t0, 2)

        if returncode != 0:
            return {
                "success": False,
                "error": f"Script exited with code {returncode}",
                "stdout": (stdout_text or "")[-3000:],
                "stderr": (stderr_text or "")[-2000:],
                "processing_time": elapsed,
            }

        # Find PKL
        pkl_path = None
        if os.path.exists(expected_pkl):
            pkl_path = expected_pkl
        else:
            cands = glob.glob(os.path.join(etl_dir, f"{etl_base}_*.pkl"))
            if cands:
                pkl_path = max(cands, key=os.path.getmtime)

        if not pkl_path:
            return {
                "success": False,
                "error": "Script succeeded but no PKL file found",
                "expected_pkl": expected_pkl,
                "processing_time": elapsed,
                "stdout": (stdout_text or "")[-3000:],
            }

        try:
            keys = list(_load_pkl(pkl_path).keys())
        except Exception:
            keys = []

        return {
            "success": True,
            "cache_hit": False,
            "pkl_file_path": pkl_path,
            "processing_time": elapsed,
            "dataframe_keys": keys,
            "script_run": script_name,
            "message": f"Analysis complete in {elapsed}s. PKL: {pkl_path}",
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"run_standalone_script failed: {_safe(exc)}",
            "traceback": traceback.format_exc(),
        }


@mcp.tool()
@async_tool
@embed_if_large(threshold=7000)
def load_dataframes_from_pickle(pickle_file_path: str, max_sample_rows: int = 50) -> Dict[str, Any]:
    """
    Load all DataFrames from a PKL file and return rich metadata including
    sample rows, column stats, and common query suggestions.

    The LLM can use this to answer most questions directly without calling
    analyze_trace_dataframe — for very large DataFrames use that tool instead.

    Args:
        pickle_file_path: Path to the PKL file (from run_standalone_script or check_analysis_pkl_exists).
        max_sample_rows:  How many rows to include per DataFrame (default 50, max 200).

    Returns:
        dataframe_summary: dict of {df_name: {shape, columns, sample_rows, stats, ...}}
        dataframe_keys, non_dataframe_keys, total_dataframes, message
    """
    try:
        if not pickle_file_path or not os.path.exists(pickle_file_path):
            return {"success": False, "error": f"PKL file not found: {pickle_file_path}"}

        # ── trace_summary PKL guard ──────────────────────────────────────────
        # Returning sample rows for df_trace_summary causes agents to narrate
        # the samples instead of running execute_python_code.  Block it.
        pkl_name = os.path.basename(pickle_file_path).lower()
        if "df_trace_summary" in pkl_name or "trace_summary" in pkl_name:
            return {
                "success": False,
                "redirect": True,
                "error": (
                    "DO NOT use load_dataframes_from_pickle for a df_trace_summary PKL. "
                    "Run execute_python_code with the ALL-IN-ONE block from your system "
                    "prompt (Step 5) instead.  The block uses pickle.load() directly and "
                    "produces proper Markdown tables.  pkl_path = " + pickle_file_path
                ),
            }
        # ── end guard ────────────────────────────────────────────────────────

        max_sample_rows = min(max(1, max_sample_rows), 200)
        data = _load_pkl(pickle_file_path)
        summary = _df_summary(data, max_sample_rows=max_sample_rows)

        df_keys = [k for k, v in summary.items() if v.get("is_dataframe")]
        other_keys = [k for k, v in summary.items() if not v.get("is_dataframe")]

        return {
            "success": True,
            "pickle_file_path": pickle_file_path,
            "dataframe_summary": summary,
            "dataframe_keys": df_keys,
            "non_dataframe_keys": other_keys,
            "total_dataframes": len(df_keys),
            "message": (
                f"Loaded {len(df_keys)} DataFrame(s) from PKL. "
                f"Use analyze_trace_dataframe() for complex queries on large DFs."
            ),
        }

    except Exception as exc:
        return {"success": False, "error": _safe(exc), "traceback": traceback.format_exc()}


@mcp.tool()
@async_tool
@embed_if_large(threshold=7000)
def get_algorithm_documentation(algorithm_name: str) -> Dict[str, Any]:
    """
    Get detailed documentation for an ETL analysis algorithm or constraint.

    Available algorithms:
        fps_calculation, vcip_alignment, comprehensive_analysis,
        containment_breach, containment_policy, cpu_frequency,
        cpu_utilization, epo_changes, hetero_parking_selection,
        hetero_response, ppm_settings, process_lifetime,
        soft_park_selection, thread_statistics, trace_loading,
        wlc_workload_classification, wps_containment_unpark

    Available constraints:
        constraints_ppm, constraints_ppm_val, constraints_teams,
        constraints_validation

    Args:
        algorithm_name: Name from the lists above.

    Returns:
        content (full markdown text), title, size_chars, file_path
    """
    _ALGORITHM_FILES = {
        "fps_calculation": "fps_calculation.md",
        "vcip_alignment": "vcip_alignment.md",
        "comprehensive_analysis": "comprehensive_analysis.md",
        "containment_breach": "containment_breach.md",
        "containment_policy": "containment_policy.md",
        "cpu_frequency": "cpu_frequency.md",
        "cpu_utilization": "cpu_utilization.md",
        "epo_changes": "epo_changes.md",
        "hetero_parking_selection": "hetero_parking_selection.md",
        "hetero_response": "hetero_response.md",
        "ppm_settings": "ppm_settings.md",
        "process_lifetime": "process_lifetime.md",
        "soft_park_selection": "soft_park_selection.md",
        "thread_statistics": "thread_statistics.md",
        "trace_loading": "trace_loading.md",
        "wlc_workload_classification": "wlc_workload_classification.md",
        "wps_containment_unpark": "wps_containment_unpark.md",
        "constraints_ppm": "constraints_ppm.md",
        "constraints_ppm_val": "constraints_ppm_val.md",
        "constraints_teams": "constraints_teams.md",
        "constraints_validation": "constraints_validation.md",
    }

    if algorithm_name not in _ALGORITHM_FILES:
        return {
            "success": False,
            "error": f"Unknown algorithm '{algorithm_name}'",
            "available": sorted(_ALGORITHM_FILES.keys()),
        }

    doc_path = ETL_DOCS_DIR / _ALGORITHM_FILES[algorithm_name]
    if not doc_path.exists():
        return {
            "success": False,
            "error": f"Documentation file not found: {doc_path}",
            "algorithm_name": algorithm_name,
        }

    try:
        content = doc_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = lines[0].lstrip("#").strip() if lines else algorithm_name
        return {
            "success": True,
            "algorithm_name": algorithm_name,
            "title": title,
            "content": content,
            "file_path": str(doc_path),
            "size_chars": len(content),
            "line_count": len(lines),
        }
    except Exception as exc:
        return {"success": False, "error": _safe(exc), "algorithm_name": algorithm_name}


@mcp.tool()
@embed_if_large(threshold=7000)
def cleanup_pickle_files(max_age_hours: int = 24, directory: str = None) -> Dict[str, Any]:
    """
    Remove old ETL analysis PKL files from a directory (default: system temp folder).

    Args:
        max_age_hours: Files older than this are deleted (default 24 h).
        directory:     Folder to clean. Defaults to the system temp folder.
                       Only files matching etl_analysis_*.pkl are removed.

    Returns:
        files_cleaned, size_cleaned_kb, cleaned_files list, message
    """
    import tempfile

    folder = directory or tempfile.gettempdir()
    max_age_sec = max_age_hours * 3600
    now = time.time()
    pattern = os.path.join(folder, "etl_analysis_*.pkl")

    cleaned, total_bytes, names = 0, 0, []
    for fp in glob.glob(pattern):
        try:
            age = now - os.path.getmtime(fp)
            if age > max_age_sec:
                sz = os.path.getsize(fp)
                os.remove(fp)
                cleaned += 1
                total_bytes += sz
                names.append(os.path.basename(fp))
        except Exception:
            pass

    return {
        "success": True,
        "files_cleaned": cleaned,
        "size_cleaned_kb": round(total_bytes / 1024, 2),
        "cleaned_files": names,
        "message": f"Cleaned {cleaned} PKL file(s), freed {round(total_bytes/1024, 2)} KB",
    }


# ---------------------------------------------------------------------------
# pregen_analysis_pkls
# ---------------------------------------------------------------------------

@mcp.tool()
@async_tool
@embed_if_large(threshold=7000)
def pregen_analysis_pkls(
    folder: str,
    scripts: List[str] = None,
    workers: int = 4,
    recursive: bool = True,
    max_size_gb: float = 0,
) -> Dict[str, Any]:
    """
    Pre-generate PKL files for all ETL traces in a folder by running standalone
    analysis scripts in parallel.

    Useful before a user session so that all analysis data is already cached and
    available instantly via check_analysis_pkl_exists.

    Args:
        folder:       Root folder to scan for .etl files (recursive by default).
        scripts:      List of script names to run, e.g. ["df_trace_summary", "wlc", "ppm"].
                      Defaults to ["df_trace_summary"] if not specified.
                      Use list_standalone_scripts() to see all available script names.
        workers:      Number of ETLs to process in parallel (default 4).
                      Use 1–2 for comprehensive_analysis (memory-heavy).
        recursive:    Scan sub-folders (default True).
        max_size_gb:  Skip ETL files larger than this in GB (0 = no limit).

    Returns:
        results per ETL per script (status: OK / CACHED / FAILED),
        summary counts, total_elapsed_seconds
    """
    try:
        if not os.path.isdir(folder):
            return {"success": False, "error": f"Folder not found: {folder}"}

        scripts = scripts or ["df_trace_summary"]
        # Normalise: strip .py, resolve aliases
        _ALIASES = {
            "trace_summary": "df_trace_summary",
            "tracesummary":  "df_trace_summary",
            "summary":       "df_trace_summary",
            "df_wlc":        "wlc",
            "df_ppm":        "ppm",
        }
        scripts = [_ALIASES.get(s.lower().rstrip(".py"), s.lower().rstrip(".py"))
                   for s in scripts]

        # Find ETLs
        pattern = os.path.join(folder, "**", "*.etl") if recursive else os.path.join(folder, "*.etl")
        etls = []
        for p in glob.glob(pattern, recursive=recursive):
            if max_size_gb > 0:
                try:
                    if os.path.getsize(p) / (1024**3) > max_size_gb:
                        continue
                except OSError:
                    pass
            etls.append(os.path.abspath(p))
        etls = sorted(etls)

        if not etls:
            return {"success": True, "message": f"No .etl files found under: {folder}",
                    "etl_count": 0, "results": {}}

        # Get speed.exe
        try:
            import speedlibs_service_client as _ssc
            speed_exe = _ssc._standalone_client.speed_exe_path
            client    = _ssc._standalone_client
        except Exception as exc:
            return {"success": False, "error": f"Cannot locate speed.exe: {exc}"}

        results: Dict[str, Dict] = {}
        _lock = threading.Lock()
        session_t0 = time.time()

        def _run_one(etl: str, script_name: str) -> None:
            etl_dir  = os.path.dirname(etl)
            etl_base = os.path.splitext(os.path.basename(etl))[0]

            # Resolve script file
            bare = script_name if not script_name.endswith(".py") else script_name[:-3]
            filename = f"standalone_{bare}.py"
            sp = ETL_STANDALONE_DIR / filename
            if not sp.exists():
                with _lock:
                    results.setdefault(etl, {})[script_name] = {
                        "status": "ERROR", "msg": f"script not found: {filename}"}
                return

            # Cache check
            if bare == "comprehensive_analysis":
                hits = glob.glob(os.path.join(etl_dir, f"{etl_base}_*_dfs.pkl"))
                cached = max(hits, key=os.path.getmtime) if hits else None
            else:
                ep = os.path.join(etl_dir, f"{etl_base}_{bare}.pkl")
                cached = ep if os.path.exists(ep) else None

            if cached:
                # Validate: reject tiny/corrupt PKLs < 10 KB
                try:
                    if os.path.getsize(cached) < 10240:
                        os.remove(cached)
                        cached = None
                except OSError:
                    cached = None

            if cached:
                with _lock:
                    results.setdefault(etl, {})[script_name] = {
                        "status": "CACHED", "pkl": cached}
                return

            # Run
            cmd = [speed_exe, "run", str(sp), "--etl_file", etl]
            t0 = time.time()
            try:
                rc, stdout, stderr = client._run_speed_exe(cmd, client.timeout_analyze)
            except Exception as exc:
                with _lock:
                    results.setdefault(etl, {})[script_name] = {
                        "status": "ERROR", "msg": str(exc)}
                return
            elapsed = round(time.time() - t0, 1)

            if rc != 0:
                with _lock:
                    results.setdefault(etl, {})[script_name] = {
                        "status": "FAILED",
                        "msg": f"exit code {rc}",
                        "stdout": (stdout or "")[-800:],
                        "elapsed": elapsed,
                    }
                return

            # Find PKL
            if bare == "comprehensive_analysis":
                hits = glob.glob(os.path.join(etl_dir, f"{etl_base}_*_dfs.pkl"))
                pkl = max(hits, key=os.path.getmtime) if hits else None
            else:
                ep = os.path.join(etl_dir, f"{etl_base}_{bare}.pkl")
                pkl = ep if os.path.exists(ep) else None
                if not pkl:
                    cands = glob.glob(os.path.join(etl_dir, f"{etl_base}_*.pkl"))
                    pkl = max(cands, key=os.path.getmtime) if cands else None

            with _lock:
                results.setdefault(etl, {})[script_name] = {
                    "status": "OK" if pkl else "FAILED",
                    "pkl": pkl,
                    "elapsed": elapsed,
                    "msg": f"done in {elapsed}s" if pkl else "no PKL produced",
                }

        # Run all (etl, script) combos in parallel
        work_items = [(etl, s) for etl in etls for s in scripts]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_one, etl, s): (etl, s) for etl, s in work_items}
            for fut in as_completed(futures):
                exc = fut.exception()
                if exc:
                    etl, s = futures[fut]
                    with _lock:
                        results.setdefault(etl, {})[s] = {"status": "ERROR", "msg": str(exc)}

        total_elapsed = round(time.time() - session_t0, 1)

        # Build summary
        counts = {"OK": 0, "CACHED": 0, "FAILED": 0, "ERROR": 0}
        per_etl = []
        for etl in etls:
            row = {"etl": etl, "basename": os.path.basename(etl)}
            for s in scripts:
                r = results.get(etl, {}).get(s, {"status": "NOT_RUN"})
                row[s] = r.get("status", "?")
                if r["status"] in counts:
                    counts[r["status"]] += 1
            per_etl.append(row)

        return {
            "success": True,
            "folder": folder,
            "etl_count": len(etls),
            "scripts": scripts,
            "workers": workers,
            "total_elapsed_seconds": total_elapsed,
            "summary_counts": counts,
            "per_etl": per_etl,
            "details": results,
            "message": (
                f"{len(etls)} ETL(s), scripts={scripts}  —  "
                f"OK={counts['OK']} CACHED={counts['CACHED']} "
                f"FAILED={counts['FAILED']}  ({total_elapsed}s total)"
            ),
        }

    except Exception as exc:
        return {"success": False, "error": _safe(exc), "traceback": traceback.format_exc()}


# ---------------------------------------------------------------------------
# list_available_analysis
# ---------------------------------------------------------------------------

@mcp.tool()
@embed_if_large(threshold=7000)
def list_available_analysis(
    folder: str,
    recursive: bool = True,
) -> Dict[str, Any]:
    """
    Scan a folder tree and report all ready-to-use PKL analysis files found
    next to each ETL trace.

    Use this to see what analysis data is already cached before deciding which
    scripts to run next, or to let the user pick which ETL/analysis to explore.

    Args:
        folder:    Root folder to scan.
        recursive: Include sub-folders (default True).

    Returns:
        per_etl list with:
          etl_path, etl_size_gb,
          available_analyses: list of {script, pkl_path, size_kb, age_minutes},
          missing_analyses:   list of known script names with no PKL yet
        summary: total_etls, total_pkls_ready, scripts_with_coverage (% ETLs covered)
    """
    try:
        if not os.path.isdir(folder):
            return {"success": False, "error": f"Folder not found: {folder}"}

        pattern = os.path.join(folder, "**", "*.etl") if recursive else os.path.join(folder, "*.etl")
        etls = sorted(glob.glob(pattern, recursive=recursive))

        if not etls:
            return {"success": True, "message": f"No .etl files found under: {folder}",
                    "etl_count": 0, "per_etl": []}

        # Known scripts to check coverage for
        known_scripts = [
            "df_trace_summary", "comprehensive_analysis",
            "wlc", "ppm", "containment", "heteroresponse",
            "cpu_freq_util", "df_threadstat", "df_processlifetime",
            "power_state", "process_stats",
        ]

        now = time.time()
        per_etl = []
        coverage: Dict[str, int] = {s: 0 for s in known_scripts}
        total_pkls = 0

        for etl in etls:
            etl_dir  = os.path.dirname(etl)
            etl_base = os.path.splitext(os.path.basename(etl))[0]
            try:
                etl_size_gb = round(os.path.getsize(etl) / (1024**3), 2)
            except OSError:
                etl_size_gb = None

            available = []
            missing   = []

            for script in known_scripts:
                # Find PKL
                if script == "comprehensive_analysis":
                    hits = glob.glob(os.path.join(etl_dir, f"{etl_base}_*_dfs.pkl"))
                    pkl = max(hits, key=os.path.getmtime) if hits else None
                else:
                    ep = os.path.join(etl_dir, f"{etl_base}_{script}.pkl")
                    pkl = ep if os.path.exists(ep) else None

                if pkl:
                    try:
                        size_kb     = round(os.path.getsize(pkl) / 1024, 1)
                        age_minutes = round((now - os.path.getmtime(pkl)) / 60, 1)
                        corrupt     = size_kb < 10   # < 10 KB = likely bad write
                    except OSError:
                        size_kb = age_minutes = 0
                        corrupt = True

                    if corrupt:
                        missing.append({"script": script, "note": "PKL exists but <10KB (corrupt)"})
                    else:
                        available.append({
                            "script":      script,
                            "pkl_path":    pkl,
                            "size_kb":     size_kb,
                            "age_minutes": age_minutes,
                        })
                        coverage[script] += 1
                        total_pkls += 1
                else:
                    missing.append({"script": script})

            per_etl.append({
                "etl_path":           etl,
                "basename":           os.path.basename(etl),
                "etl_size_gb":        etl_size_gb,
                "available_analyses": available,
                "available_count":    len(available),
                "missing_analyses":   missing,
                "missing_count":      len(missing),
            })

        # Coverage summary
        n = len(etls)
        script_coverage = [
            {"script": s, "etls_with_pkl": coverage[s],
             "coverage_pct": round(coverage[s] / n * 100)}
            for s in known_scripts
        ]

        return {
            "success":          True,
            "folder":           folder,
            "etl_count":        n,
            "total_pkls_ready": total_pkls,
            "per_etl":          per_etl,
            "script_coverage":  script_coverage,
            "message": (
                f"{n} ETL(s) found, {total_pkls} PKL(s) ready.  "
                + "  ".join(
                    f"{s['script']}: {s['coverage_pct']}%"
                    for s in script_coverage if s['etls_with_pkl'] > 0
                )
            ),
        }

    except Exception as exc:
        return {"success": False, "error": _safe(exc), "traceback": traceback.format_exc()}
