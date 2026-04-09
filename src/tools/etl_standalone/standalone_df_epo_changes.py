"""
Standalone: df_epo_changes
============================
Extracts Effective Power Overlay (EPO) / power scheme change events
from EsifUmdf2EtwProvider ETW messages containing "Setting power scheme".
Parses GUID and scheme value from each message using regex.

PKL: <etl_basename>_df_epo_changes.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_df_epo_changes.py --etl_file <path>

PKL keys:
    df_epo_changes — columns: timestamp, message, guid, value
"""
import sys, os, argparse, pickle, re
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

PKL_SUFFIX = "df_epo_changes"

_GUID_RE  = re.compile(r"\{([0-9a-fA-F-]{36})\}")
_VALUE_RE = re.compile(r"Overlay Value\s*[=:]\s*([0-9a-zA-Z_]+)", re.IGNORECASE)

def _pkl_path(etl):
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def extract(trace):
    rows = []
    try:
        for ev in trace.get_events(event_types=["EsifUmdf2EtwProvider//win:Info"]):
            try:
                msg = ev.get("Message", ev.get("message", ""))
                if "Setting power scheme" not in msg: continue
                ts  = ev.get("TimeStamp", 0) / 1000000
                gm  = _GUID_RE.search(msg)
                vm  = _VALUE_RE.search(msg)
                rows.append({
                    "timestamp": ts,
                    "message":   msg,
                    "guid":      gm.group(1) if gm else "",
                    "value":     vm.group(1) if vm else "",
                })
            except Exception:
                pass
    except Exception as e:
        print(f"[WARNING] extract error: {e}")
    df = pd.DataFrame(rows)
    print(f"[df_epo_changes] {len(df)} records")
    return df

def main():
    ap = argparse.ArgumentParser(description="Standalone df_epo_changes (speed.exe)")
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
        "df_epo_changes": extract(trace),
        "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                 "timestamp": datetime.now().isoformat()},
    }
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
