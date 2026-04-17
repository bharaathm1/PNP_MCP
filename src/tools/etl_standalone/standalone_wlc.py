"""
Standalone WLC & Expected Utility Analysis Script
===================================================
Targeted script: extracts Workload Classification (WLC) and
ExpectedUtility events.
Use when the user asks about workload classification, expected vs actual
scheduler utility, or SOCWC classification events.

PKL output: <etl_basename>_wlc.pkl  (same folder as ETL)
Cache check: if the PKL already exists, exits immediately — no re-parse.

Usage:
    speed.exe run standalone_wlc.py --etl_file <path>

Output keys in PKL:
    df_wlc             - SOCWC classification events (timestamp, wlc status)
    df_wlc_histogram   - Forward-filled 1ms histogram; columns:
                         wlc (int), state (str), duration_ms (int),
                         duration_s (float), pct (float)
                         States: 0=Idle, 1=BatteryLife, 2=Sustained, 3=Bursty
    df_expectedutility - ExpectedUtility vs ActualUtility per interval
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

PKL_SUFFIX = "wlc"


def _pkl_path(etl_file_path: str) -> str:
    etl_dir  = os.path.dirname(os.path.abspath(etl_file_path))
    basename = os.path.splitext(os.path.basename(etl_file_path))[0]
    return os.path.join(etl_dir, f"{basename}_{PKL_SUFFIX}.pkl")


def extract_wlc(trace):
    try:
        ts, status = [], []
        for ev in trace.get_events(event_types=["DptfCpuEtwProvider//win:Info"]):
            try:
                if ev["String"] == "SOCWC classification = ":
                    ts.append(ev["TimeStamp"] / 1000000)
                    status.append(ev["Status"])
            except Exception:
                pass
        df = pd.DataFrame({"timestamp": ts, "wlc": status})
        print(f"[WLC] wlc events: {len(df)}")
        return df
    except Exception as e:
        print(f"[WARNING] wlc error: {e}")
        return pd.DataFrame()


def extract_expected_utility(trace):
    try:
        ts, exp_util, act_util = [], [], []
        for ev in trace.get_events(
                event_types=["Microsoft-Windows-Kernel-Processor-Power/ExpectedUtility/win:Info"]):
            try:
                eu = ev.get("EstimatedUtility", [])
                au = ev.get("ActualUtility", [])
                ts.append(ev["TimeStamp"] / 1000000)
                exp_util.append(max(eu) if isinstance(eu, list) and eu else (eu or 0))
                act_util.append(max(au) if isinstance(au, list) and au else (au or 0))
            except Exception:
                if ts: ts.pop()
        df = pd.DataFrame({"timestamp": ts, "expectedUtility": exp_util, "actualUtility": act_util})
        print(f"[WLC] expectedutility: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARNING] expectedutility error: {e}")
        return pd.DataFrame()


WLC_LABELS = {0: "Idle", 1: "BatteryLife", 2: "Sustained", 3: "Bursty"}


def compute_wlc_histogram(df_wlc: pd.DataFrame) -> pd.DataFrame:
    """
    Forward-fill WLC state at 1ms granularity across the trace window,
    then compute a residency histogram.
    States: 0=Idle, 1=BatteryLife, 2=Sustained, 3=Bursty
    """
    if df_wlc.empty:
        return pd.DataFrame()

    df = df_wlc.sort_values("timestamp").reset_index(drop=True)

    # Build a 1ms-resolution index
    t_start_ms = int(df["timestamp"].iloc[0] * 1000)
    t_end_ms   = int(df["timestamp"].iloc[-1] * 1000) + 1
    n_cells    = t_end_ms - t_start_ms

    if n_cells <= 0:
        return pd.DataFrame()

    # Place each event into its 1ms cell, then forward-fill
    states = np.full(n_cells, np.nan)
    for _, row in df.iterrows():
        idx = int(row["timestamp"] * 1000) - t_start_ms
        if 0 <= idx < n_cells:
            states[idx] = row["wlc"]

    # Forward fill (carry last known state), back-fill leading NaNs
    s = pd.Series(states).ffill().bfill()

    total = len(s)
    rows = []
    for state_val, label in sorted(WLC_LABELS.items()):
        count = int((s == state_val).sum())
        pct   = round(count / total * 100, 2) if total > 0 else 0.0
        rows.append({
            "wlc":         state_val,
            "state":       label,
            "duration_ms": count,
            "duration_s":  round(count / 1000, 3),
            "pct":         pct,
        })

    df_hist = pd.DataFrame(rows)
    print(f"[WLC] histogram: {total} ms window | "
          f"states observed: {sorted(df['wlc'].unique().tolist())}")
    return df_hist


def main():
    parser = argparse.ArgumentParser(description="Standalone WLC Analysis (speed.exe)")
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

    df_wlc = extract_wlc(trace)
    df_wlc_histogram = compute_wlc_histogram(df_wlc)

    results = {
        "df_wlc":             df_wlc,
        "df_wlc_histogram":   df_wlc_histogram,
        "df_expectedutility": extract_expected_utility(trace),
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
