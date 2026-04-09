"""
Standalone: df_cpu_concurrency
================================
Extracts CPU thread concurrency data using trace.get_cpu_concurrency().
Shows how many threads are simultaneously running on the CPU over time.

PKL: <etl_basename>_df_cpu_concurrency.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_df_cpu_concurrency.py --etl_file <path>

PKL keys:
    df_cpu_concurrency — columns: timestamp, Concurency (thread count over time)
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

PKL_SUFFIX = "df_cpu_concurrency"

def _pkl_path(etl):
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def extract(trace):
    try:
        if not hasattr(trace, "get_cpu_concurrency"):
            print("[WARNING] get_cpu_concurrency not available"); return pd.DataFrame()
        data = trace.get_cpu_concurrency()
        if data is None: return pd.DataFrame()
        df = data.to_dataframe() if hasattr(data, "to_dataframe") else pd.DataFrame(data)
        if not df.empty:
            if "Start(s)" in df.columns: df.rename(columns={"Start(s)": "timestamp"}, inplace=True)
            if "Count" in df.columns:    df.rename(columns={"Count": "Concurency"}, inplace=True)
            df.drop(columns=["End(s)", "Duration(s)"], errors="ignore", inplace=True)
        print(f"[df_cpu_concurrency] {df.shape}")
        return df
    except Exception as e:
        print(f"[WARNING] extract error: {e}"); return pd.DataFrame()

def main():
    ap = argparse.ArgumentParser(description="Standalone df_cpu_concurrency (speed.exe)")
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
    results = {
        "df_cpu_concurrency": extract(trace),
        "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                 "timestamp": datetime.now().isoformat()},
    }
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
