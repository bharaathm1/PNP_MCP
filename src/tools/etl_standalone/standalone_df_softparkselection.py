"""
Standalone: df_softparkselection
==================================
Extracts SoftParkSelection events: OldPark, NewPark, NewSoftPark bitmasks.
Shows which CPU cores transition between parked/unparked states.

PKL: <etl_basename>_df_softparkselection.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_df_softparkselection.py --etl_file <path>

PKL keys:
    df_softparkselection — columns: timestamp, OldPark, NewPark, NewSoftPark
                           (bitmask values as binary strings)
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

PKL_SUFFIX = "df_softparkselection"

def _pkl_path(etl):
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def extract(trace):
    ts, old_p, new_p, new_sp = [], [], [], []
    try:
        for i in trace.get_events(
                event_types=["Microsoft-Windows-Kernel-Processor-Power/SoftParkSelection/win:Info"]):
            try:
                ts.append(i["TimeStamp"] / 1000000)
                old_p.append(bin(int(i["OldPark"], 16)))
                new_p.append(bin(int(i["NewPark"], 16)))
                new_sp.append(bin(int(i["NewSoftPark"], 16)))
            except Exception:
                pass
    except Exception as e:
        print(f"[WARNING] extract error: {e}")
    df = pd.DataFrame({"timestamp": ts, "OldPark": old_p, "NewPark": new_p, "NewSoftPark": new_sp})
    print(f"[df_softparkselection] {len(df)} records")
    return df

def main():
    ap = argparse.ArgumentParser(description="Standalone df_softparkselection (speed.exe)")
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
        "df_softparkselection": extract(trace),
        "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                 "timestamp": datetime.now().isoformat()},
    }
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
