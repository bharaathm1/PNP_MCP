"""
Standalone CPU Frequency / Utilization / Concurrency Analysis Script
======================================================================
Targeted script: extracts CPU-level performance data.
Use when the user asks about CPU utilization per core, per-core frequencies,
or CPU thread concurrency.

PKL output: <etl_basename>_cpu_freq_util.pkl  (same folder as ETL)
Cache check: if the PKL already exists, exits immediately — no re-parse.

Usage:
    speed.exe run standalone_cpu_freq_util.py --etl_file <path>

Output keys in PKL:
    df_cpu_util   - per-core CPU utilization intervals
    df_cpu_freq   - per-core CPU frequency (GHz) over time
    df_cpu_con    - CPU concurrency (thread count) over time
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

PKL_SUFFIX = "cpu_freq_util"


def _pkl_path(etl_file_path: str) -> str:
    etl_dir  = os.path.dirname(os.path.abspath(etl_file_path))
    basename = os.path.splitext(os.path.basename(etl_file_path))[0]
    return os.path.join(etl_dir, f"{basename}_{PKL_SUFFIX}.pkl")


def extract_cpu_util(trace):
    try:
        if not hasattr(trace, "get_cpu_utilization"):
            print("[WARNING] get_cpu_utilization not available")
            return pd.DataFrame()
        data = trace.get_cpu_utilization()
        if data is None:
            return pd.DataFrame()
        df = data.to_dataframe() if hasattr(data, "to_dataframe") else pd.DataFrame(data)
        if "timestamp" not in df.columns:
            df = df.reset_index().rename(columns={"index": "timestamp"})
        print(f"[CPU] utilization: {df.shape}")
        return df
    except Exception as e:
        print(f"[WARNING] cpu_util error: {e}")
        return pd.DataFrame()


def extract_cpu_freq(trace):
    try:
        if not hasattr(trace, "get_cpu_frequencies"):
            print("[WARNING] get_cpu_frequencies not available")
            return pd.DataFrame()
        data = trace.get_cpu_frequencies()
        if data is None:
            return pd.DataFrame()
        df = data.to_dataframe() if hasattr(data, "to_dataframe") else pd.DataFrame(data)
        if "CPU" in df.columns and "Start(s)" in df.columns and "Frequency(Hz)" in df.columns:
            per_core = []
            for cpu in sorted(df["CPU"].unique()):
                cdf = df[df["CPU"] == cpu].copy()
                cdf = cdf.rename(columns={"Start(s)": "timestamp",
                                           "Frequency(Hz)": f"CPU_{cpu}_Freq"})
                cdf[f"CPU_{cpu}_Freq"] /= 1e9  # Hz → GHz
                cdf.drop(columns=["CPU", "End(s)", "Duration(s)"], errors="ignore", inplace=True)
                per_core.append(cdf)
            if per_core:
                merged = per_core[0]
                for c in per_core[1:]:
                    merged = pd.merge(merged, c, on="timestamp", how="outer")
                print(f"[CPU] frequency: {merged.shape}")
                return merged
        print(f"[CPU] frequency: {df.shape}")
        return df
    except Exception as e:
        print(f"[WARNING] cpu_freq error: {e}")
        return pd.DataFrame()


def extract_cpu_con(trace):
    try:
        if not hasattr(trace, "get_cpu_concurrency"):
            print("[WARNING] get_cpu_concurrency not available")
            return pd.DataFrame()
        data = trace.get_cpu_concurrency()
        if data is None:
            return pd.DataFrame()
        df = data.to_dataframe() if hasattr(data, "to_dataframe") else pd.DataFrame(data)
        if not df.empty:
            if "Start(s)" in df.columns:
                df.rename(columns={"Start(s)": "timestamp"}, inplace=True)
            if "Count" in df.columns:
                df.rename(columns={"Count": "Concurency"}, inplace=True)
            df.drop(columns=["End(s)", "Duration(s)"], errors="ignore", inplace=True)
        print(f"[CPU] concurrency: {df.shape}")
        return df
    except Exception as e:
        print(f"[WARNING] cpu_con error: {e}")
        return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description="Standalone CPU Freq/Util Analysis (speed.exe)")
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
        "df_cpu_util": extract_cpu_util(trace),
        "df_cpu_freq": extract_cpu_freq(trace),
        "df_cpu_con":  extract_cpu_con(trace),
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
