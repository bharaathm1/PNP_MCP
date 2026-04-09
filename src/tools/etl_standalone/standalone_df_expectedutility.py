"""
Standalone: df_expectedutility
================================
Extracts ExpectedUtility vs ActualUtility per scheduling interval.
Shows discrepancy between what the scheduler expected and what happened.

PKL: <etl_basename>_df_expectedutility.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_df_expectedutility.py --etl_file <path>

PKL keys:
    df_expectedutility — columns: timestamp, expectedUtility, actualUtility
"""
import sys, os, argparse, pickle
from datetime import datetime
from pathlib import Path

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

PKL_SUFFIX = "df_expectedutility"

def _pkl_path(etl):
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def extract(trace):
    ts, exp, act = [], [], []
    try:
        for ev in trace.get_events(
                event_types=["Microsoft-Windows-Kernel-Processor-Power/ExpectedUtility/win:Info"]):
            try:
                eu = ev.get("EstimatedUtility", [])
                au = ev.get("ActualUtility", [])
                ts.append(ev["TimeStamp"] / 1000000)
                exp.append(max(eu) if isinstance(eu, list) and eu else (eu or 0))
                act.append(max(au) if isinstance(au, list) and au else (au or 0))
            except Exception:
                if ts: ts.pop()
    except Exception as e:
        print(f"[WARNING] extract error: {e}")
    df = pd.DataFrame({"timestamp": ts, "expectedUtility": exp, "actualUtility": act})
    print(f"[df_expectedutility] {len(df)} records")
    return df

def main():
    ap = argparse.ArgumentParser(description="Standalone df_expectedutility (speed.exe)")
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
        "df_expectedutility": extract(trace),
        "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                 "timestamp": datetime.now().isoformat()},
    }
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
