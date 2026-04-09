"""
Custom Standalone: hetero_parking_selection_schema_safe
=========================================================
Discover all fields for Microsoft-Windows-Kernel-Processor-Power/HeteroParkingSelectionCount/win:Info events by dumping all key/value pairs from sample events into a DataFrame.

PKL: <etl_basename>_hetero_parking_selection_schema_safe.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.
"""
import sys, os, argparse, pickle
from datetime import datetime

_SPEEDLIBS = r"D:\bharath_working_directory\share\agents\SpeedLibs"
if _SPEEDLIBS not in sys.path:
    sys.path.insert(0, _SPEEDLIBS)

import pandas as pd
import numpy as np
if not hasattr(np, "int"):
    np.int = int; np.float = float; np.complex = complex; np.bool = bool

try:
    import tracedm
except ImportError as e:
    print(f"[ERROR] {e}"); sys.exit(1)

PKL_SUFFIX = "hetero_parking_selection_schema_safe"


def _pkl_path(etl: str) -> str:
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")


def run_analysis(trace, etl_file_path: str) -> dict:
    """User-provided analysis logic."""
    import numpy as np
    from datetime import datetime

    PROVIDER_EVENT = "Microsoft-Windows-Kernel-Processor-Power/HeteroParkingSelectionCount/win:Info"

    rows = []
    max_samples = 50

    print(f"[SCAN] event_types=[{PROVIDER_EVENT}]")
    for ev in trace.get_events(event_types=[PROVIDER_EVENT]):
        ts = ev.get("TimeStamp", None)
        if ts is not None:
            ts = ts / 1_000_000.0

        row = {"timestamp": ts}
        for k, v in ev.items():
            if k == "TimeStamp":
                continue
            row[k] = v

        rows.append(row)
        if len(rows) >= max_samples:
            break

    if not rows:
        print("[INFO] No HeteroParkingSelectionCount events found.")
        df_hetero_parking_selection_schema_safe = pd.DataFrame(columns=["timestamp"])
    else:
        df_hetero_parking_selection_schema_safe = pd.DataFrame(rows)
        cols = ["timestamp"] + [c for c in df_hetero_parking_selection_schema_safe.columns if c != "timestamp"]
        df_hetero_parking_selection_schema_safe = df_hetero_parking_selection_schema_safe[cols]
        print(f"[OK] collected {len(df_hetero_parking_selection_schema_safe)} events; discovered columns:")
        for c in df_hetero_parking_selection_schema_safe.columns:
            print("  -", c)

    return {"df_hetero_parking_selection_schema_safe": df_hetero_parking_selection_schema_safe}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etl_file", required=True)
    args = ap.parse_args()
    if not os.path.exists(args.etl_file):
        print(f"[ERROR] Not found: {args.etl_file}"); sys.exit(1)
    pkl = _pkl_path(args.etl_file)
    if os.path.exists(pkl):
        print(f"[CACHE HIT] {pkl}"); print(f"[OUTPUT_PKL] {pkl}"); sys.exit(0)
    trace = tracedm.load_trace(etl_file=args.etl_file)
    data = run_analysis(trace, args.etl_file)
    data["meta"] = {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                     "timestamp": datetime.now().isoformat()}
    with open(pkl, "wb") as f:
        pickle.dump(data, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")


if __name__ == "__main__":
    main()
