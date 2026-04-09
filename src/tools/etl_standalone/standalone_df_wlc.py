"""
Standalone: df_wlc
====================
Extracts WLC (Workload Classification / SOCWC) events from ETL trace.
Each event captures the SOCWC classification status at a point in time.

PKL: <etl_basename>_df_wlc.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_df_wlc.py --etl_file <path>

PKL keys:
    df_wlc  — columns: timestamp (ms), wlc (SOCWC classification status)
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

PKL_SUFFIX = "df_wlc"

def _pkl_path(etl):
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def extract(trace):
    ts, status = [], []
    try:
        for ev in trace.get_events(event_types=["DptfCpuEtwProvider//win:Info"]):
            try:
                if ev["String"] == "SOCWC classification = ":
                    ts.append(ev["TimeStamp"] / 1000000)
                    status.append(ev["Status"])
            except Exception:
                pass
    except Exception as e:
        print(f"[WARNING] extract error: {e}")
    df = pd.DataFrame({"timestamp": ts, "wlc": status})
    print(f"[df_wlc] {len(df)} records")
    return df

def main():
    ap = argparse.ArgumentParser(description="Standalone df_wlc (speed.exe)")
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
        "df_wlc": extract(trace),
        "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                 "timestamp": datetime.now().isoformat()},
    }
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
