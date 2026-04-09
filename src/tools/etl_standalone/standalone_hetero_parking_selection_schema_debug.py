"""
Custom Standalone: hetero_parking_selection_schema_debug
==========================================================
Robust schema discovery for Microsoft-Windows-Kernel-Processor-Power/HeteroParkingSelectionCount/win:Info, logging event_seen and event_errors.

PKL: <etl_basename>_hetero_parking_selection_schema_debug.pkl  (same folder as ETL)
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

PKL_SUFFIX = "hetero_parking_selection_schema_debug"


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
    event_seen = 0
    event_errors = 0
    max_samples = 50

    print(f"[SCAN] Calling trace.get_events(event_types=[{PROVIDER_EVENT!r}])")

    try:
        ev_iter = trace.get_events(event_types=[PROVIDER_EVENT])
    except Exception as e:
        print(f"[FATAL] get_events() failed: {e}")
        df_hetero_parking_selection_schema_debug = pd.DataFrame(columns=["timestamp"])
    else:
        for idx, ev in enumerate(ev_iter):
            event_seen += 1
            try:
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
            except Exception as e:
                event_errors += 1
                print(f"[WARN] Error processing event #{idx}: {e}")

        if not rows:
            print(f"[INFO] Scan done. event_seen={event_seen}, event_errors={event_errors}")
            df_hetero_parking_selection_schema_debug = pd.DataFrame(columns=["timestamp"])
        else:
            df_hetero_parking_selection_schema_debug = pd.DataFrame(rows)
            cols = ["timestamp"] + [c for c in df_hetero_parking_selection_schema_debug.columns if c != "timestamp"]
            df_hetero_parking_selection_schema_debug = df_hetero_parking_selection_schema_debug[cols]
            print(f"[OK] collected {len(df_hetero_parking_selection_schema_debug)} rows from {event_seen} events; errors={event_errors}")
            print("[INFO] Discovered columns:")
            for c in df_hetero_parking_selection_schema_debug.columns:
                print("  -", c)

    # Also stash simple meta into the PKL via the standard 'meta' object
    meta = {
        "analysis": "hetero_parking_selection_schema_debug",
        "provider_event": PROVIDER_EVENT,
        "event_seen": event_seen,
        "event_errors": event_errors,
        "timestamp": datetime.now().isoformat(),
    }
    return {"df_hetero_parking_selection_schema_debug": df_hetero_parking_selection_schema_debug}


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
