"""
Standalone Process & Thread Stats Analysis Script
===================================================
Targeted script: extracts process lifetime events and thread intervals.
Use when the user asks about process scheduling, top threads,
process start/stop events, or thread run-time statistics.

PKL output: <etl_basename>_process_stats.pkl  (same folder as ETL)
Cache check: if the PKL already exists, exits immediately — no re-parse.

Usage:
    speed.exe run standalone_process_stats.py --etl_file <path>

Output keys in PKL:
    df_processlifetime  - process start/stop events
    df_thread_interval  - per-thread run-time intervals
"""

import sys
import os
import argparse
import pickle
from datetime import datetime
from pathlib import Path

speedlibs_project_path = r"D:\bharath_working_directory\share\agents\SpeedLibs"
if speedlibs_project_path not in sys.path:
    sys.path.insert(0, speedlibs_project_path)

import pandas as pd
import numpy as np

if not hasattr(np, 'int'):
    np.int = int; np.float = float; np.complex = complex; np.bool = bool

try:
    import tracedm
    SPEED_AVAILABLE = True
    print("[OK] SPEED kernel loaded")
except ImportError as e:
    print(f"[ERROR] SPEED kernel not available: {e}")
    sys.exit(1)

PKL_SUFFIX = "process_stats"


def _pkl_path(etl_file_path: str) -> str:
    etl_dir  = os.path.dirname(os.path.abspath(etl_file_path))
    basename = os.path.splitext(os.path.basename(etl_file_path))[0]
    return os.path.join(etl_dir, f"{basename}_{PKL_SUFFIX}.pkl")


def extract_processlifetime(trace):
    try:
        if not hasattr(trace, "get_processes"):
            print("[WARNING] get_processes not available")
            return pd.DataFrame()
        data = trace.get_processes()
        if data is None:
            return pd.DataFrame()
        df = data.to_dataframe() if hasattr(data, "to_dataframe") else pd.DataFrame(data)
        if "timestamp" not in df.columns:
            df = df.reset_index()
            if "index" in df.columns:
                df.rename(columns={"index": "timestamp"}, inplace=True)
        print(f"[PROC] processlifetime: {df.shape}")
        return df
    except Exception as e:
        print(f"[WARNING] processlifetime error: {e}")
        return pd.DataFrame()


def extract_thread_intervals(trace):
    try:
        if not hasattr(trace, "get_thread_intervals"):
            print("[WARNING] get_thread_intervals not available")
            return pd.DataFrame()
        data = trace.get_thread_intervals()
        if data is None:
            return pd.DataFrame()
        df = data.to_dataframe() if hasattr(data, "to_dataframe") else pd.DataFrame(data)
        if "timestamp" not in df.columns:
            df = df.reset_index()
            if "index" in df.columns:
                df.rename(columns={"index": "timestamp"}, inplace=True)
        print(f"[PROC] thread_interval: {df.shape}")
        return df
    except Exception as e:
        print(f"[WARNING] thread_interval error: {e}")
        return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description="Standalone Process/Thread Stats Analysis (speed.exe)")
    parser.add_argument("--etl_file", required=True)
    args = parser.parse_args()

    if not os.path.exists(args.etl_file):
        print(f"[ERROR] ETL file not found: {args.etl_file}")
        sys.exit(1)

    pkl = _pkl_path(args.etl_file)

    if os.path.exists(pkl):
        print(f"[CACHE HIT] PKL already exists, skipping re-analysis.")
        print(f"[OUTPUT_PKL] {pkl}")
        sys.exit(0)

    print(f"[LOAD] Loading trace: {args.etl_file}")
    trace = tracedm.load_trace(etl_file=args.etl_file)
    print(f"[LOAD] OK — {type(trace).__name__}")

    results = {
        "df_processlifetime": extract_processlifetime(trace),
        "df_thread_interval": extract_thread_intervals(trace),
        "meta": {
            "analysis": PKL_SUFFIX,
            "etl_file": args.etl_file,
            "timestamp": datetime.now().isoformat(),
        },
    }

    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] PKL saved: {pkl}")
    print(f"[OUTPUT_PKL] {pkl}")
    sys.exit(0)


if __name__ == "__main__":
    main()
