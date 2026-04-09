"""
Standalone: df_trace_summary
==============================
Extracts a full trace summary using PPAApi trace_summary() with all sub-analyses
(threads, interrupts, GPU, disk). Produces 5 key DataFrames in a single PKL.

PKL: <etl_basename>_df_trace_summary.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_df_trace_summary.py --etl_file <path>

PKL keys:
    df_utilization_per_logical  — per-logical-CPU utilization
    df_process_stats            — per-process CPU stats
    df_qos_per_process          — QoS breakdown per process
    df_qos_per_core             — QoS breakdown per core
    df_cpu_frequency_stats      — CPU frequency statistics
"""
import sys, os, argparse, pickle
from datetime import datetime

_SPEEDLIBS = r"D:\bharath_working_directory\share\agents\SpeedLibs"
if _SPEEDLIBS not in sys.path:
    sys.path.insert(0, _SPEEDLIBS)

import pandas as pd
import numpy as np
if not hasattr(np, 'int'):
    np.int = int; np.float = float; np.complex = complex; np.bool = bool

try:
    import tracedm
    print("[OK] SPEED kernel loaded")
except ImportError as e:
    print(f"[ERROR] {e}"); sys.exit(1)

try:
    from ppa.analysis.summary import trace_summary
    print("[OK] trace_summary imported")
except ImportError as e:
    print(f"[WARNING] trace_summary not available: {e}")
    trace_summary = None

PKL_SUFFIX = "df_trace_summary"

def _pkl_path(etl):
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def _safe_to_df(obj, name):
    """Convert a trace_summary attribute object to a DataFrame."""
    try:
        if obj is None: return pd.DataFrame()
        if isinstance(obj, pd.DataFrame): return obj
        if hasattr(obj, "to_dataframe"): return obj.to_dataframe()
        if hasattr(obj, "to_pandas"): return obj.to_pandas()
        df = pd.DataFrame(obj)
        print(f"[{name}] {df.shape}")
        return df
    except Exception as e:
        print(f"[WARNING] {name} to_df failed: {e}")
        return pd.DataFrame()

def extract(trace):
    if trace_summary is None:
        print("[WARNING] trace_summary unavailable — returning empty DFs")
        return {k: pd.DataFrame() for k in [
            "df_utilization_per_logical","df_process_stats",
            "df_qos_per_process","df_qos_per_core","df_cpu_frequency_stats"]}
    try:
        ts = trace_summary(trace, threads=True, interrupts=True, gpu=True, disk=True)
        result = {
            "df_utilization_per_logical": _safe_to_df(getattr(ts, "utilization_per_logical", None), "utilization_per_logical"),
            "df_process_stats":           _safe_to_df(getattr(ts, "process_stats", None),           "process_stats"),
            "df_qos_per_process":         _safe_to_df(getattr(ts, "qos_per_process", None),         "qos_per_process"),
            "df_qos_per_core":            _safe_to_df(getattr(ts, "qos_per_core", None),            "qos_per_core"),
            "df_cpu_frequency_stats":     _safe_to_df(getattr(ts, "cpu_frequency_stats", None),     "cpu_frequency_stats"),
        }
        return result
    except Exception as e:
        print(f"[WARNING] trace_summary call failed: {e}")
        return {k: pd.DataFrame() for k in [
            "df_utilization_per_logical","df_process_stats",
            "df_qos_per_process","df_qos_per_core","df_cpu_frequency_stats"]}

def main():
    ap = argparse.ArgumentParser(description="Standalone df_trace_summary (speed.exe)")
    ap.add_argument("--etl_file", required=True)
    args = ap.parse_args()
    if not os.path.exists(args.etl_file):
        print(f"[ERROR] Not found: {args.etl_file}"); sys.exit(1)
    pkl = _pkl_path(args.etl_file)
    if os.path.exists(pkl):
        print(f"[CACHE HIT] {pkl}"); print(f"[OUTPUT_PKL] {pkl}"); sys.exit(0)
    print(f"[LOAD] {args.etl_file}")
    trace = tracedm.load_trace(etl_file=args.etl_file)
    print(f"[LOAD] OK — {type(trace).__name__}")
    data = extract(trace)           # dict of 5 DFs
    results = {**data, "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                                "timestamp": datetime.now().isoformat()}}
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
