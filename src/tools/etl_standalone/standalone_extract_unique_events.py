"""
Custom Standalone: extract_unique_events
==========================================
Extracts all unique events in an ETL trace without filtering by providers and collects their event types.

PKL: <etl_basename>_extract_unique_events.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_extract_unique_events.py --etl_file <path>

PKL keys:
    unique_events — primary output (see description)
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
    print("[OK] SPEED kernel loaded")
except ImportError as e:
    print(f"[ERROR] {e}"); sys.exit(1)

PKL_SUFFIX = "extract_unique_events"


def _pkl_path(etl: str) -> str:
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")


def run_analysis(trace, etl_file_path: str) -> dict:
    """User-provided analysis logic. Must assign variable 'unique_events'."""
    # --- USER-PROVIDED LOGIC ---
    from collections import Counter
    counts = Counter()
    for ev in trace.get_events():
        try:
            # SPEED kernel events are dict-like — use ev["Key"] not ev.attribute
            try:
                provider = ev["ProviderName"]
            except Exception:
                provider = "Unknown"
            try:
                event_name = ev["EventName"]
            except Exception:
                event_name = "Unknown"
            key = f"{provider}/{event_name}"
            counts[key] += 1
        except Exception:
            pass
    unique_events = pd.DataFrame(
        [{"event_type": et, "count": c} for et, c in sorted(counts.items())]
    )
    print(f"[extract_unique_events] {len(unique_events)} unique event types, "
          f"{unique_events['count'].sum() if len(unique_events) else 0:,} total events")
    # --- END USER LOGIC ---
    return {"unique_events": unique_events}


def main():
    ap = argparse.ArgumentParser(description="Custom Standalone: extract_unique_events (speed.exe)")
    ap.add_argument("--etl_file", required=True)
    args = ap.parse_args()
    if not os.path.exists(args.etl_file):
        print(f"[ERROR] Not found: {args.etl_file}"); sys.exit(1)
    pkl = _pkl_path(args.etl_file)
    if os.path.exists(pkl):
        # Guard: if cached PKL has empty unique_events, delete & re-run
        try:
            with open(pkl, "rb") as _f:
                _cached = pickle.load(_f)
            _ue = _cached.get("unique_events")
            if _ue is not None and hasattr(_ue, "__len__") and len(_ue) == 0:
                print(f"[CACHE STALE] Empty unique_events in {pkl} — re-running")
                os.remove(pkl)
            else:
                print(f"[CACHE HIT] {pkl}"); print(f"[OUTPUT_PKL] {pkl}"); sys.exit(0)
        except Exception as _e:
            print(f"[CACHE CHECK FAILED] {_e} — re-running")
    print(f"[LOAD] {args.etl_file}")
    trace = tracedm.load_trace(etl_file=args.etl_file)
    print(f"[LOAD] OK — {type(trace).__name__}")
    data = run_analysis(trace, args.etl_file)
    results = {**data, "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                                 "timestamp": datetime.now().isoformat()}}
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")


if __name__ == "__main__":
    main()
