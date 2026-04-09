"""
Standalone: df_heteroresponse
================================
Extracts HeteroResponse events: estimated vs actual CPU utility per interval
and the scheduler decision (P-core vs E-core assignment).

PKL: <etl_basename>_df_heteroresponse.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_df_heteroresponse.py --etl_file <path>

PKL keys:
    df_heteroresponse — columns: timestamp, EstimatedUtility, ActualUtility,
                                  ActiveTime, decision
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

PKL_SUFFIX = "df_heteroresponse"

def _pkl_path(etl):
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def extract(trace):
    ts, et, at, active, dec = [], [], [], [], []
    try:
        for i in trace.get_events(
                event_types=["Microsoft-Windows-Kernel-Processor-Power/HeteroResponse/win:Info"]):
            try:
                ts.append(i["TimeStamp"] / 1000000)
                et.append(max(i["EstimatedUtility"]))
                at.append(max(i["ActualUtility"]))
                active.append(i["ActiveTime"])
                dec.append(i["Decision"])
            except Exception:
                pass
    except Exception as e:
        print(f"[WARNING] extract error: {e}")
    df = pd.DataFrame({"timestamp": ts, "EstimatedUtility": et, "ActualUtility": at,
                       "ActiveTime": active, "decision": dec})
    print(f"[df_heteroresponse] {len(df)} records")
    return df

def main():
    ap = argparse.ArgumentParser(description="Standalone df_heteroresponse (speed.exe)")
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
        "df_heteroresponse": extract(trace),
        "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                 "timestamp": datetime.now().isoformat()},
    }
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
