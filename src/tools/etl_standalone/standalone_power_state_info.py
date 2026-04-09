"""
Standalone: power_state_info
==============================
Extracts system power state information from RundownPowerSource and
RundownEffectiveOverlayPowerScheme ETW events.
Maps power scheme GUIDs to human-readable names.

PKL: <etl_basename>_power_state_info.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_power_state_info.py --etl_file <path>

PKL keys:
    power_state_info — dict with keys:
        power_source        : "AC" / "DC" / "Unknown"
        effective_scheme    : GUID string or "Unknown"
        scheme_name         : human-readable scheme name
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

PKL_SUFFIX = "power_state_info"

GUID_MAPPING = {
    "381b4222-f694-41f0-9685-ff5bb260df2e": "Balanced",
    "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "High Performance",
    "a1841308-3541-4fab-bc81-f71556f20b4a": "Power Saver",
    "ded574b5-45a0-4f42-8734-20b7b9de68e6": "Optimized Battery (Overlay)",
    "00000000-0000-0000-0000-000000000000": "No active scheme",
}

def _pkl_path(etl):
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def extract(trace):
    info = {"power_source": "Unknown", "effective_scheme": "Unknown", "scheme_name": "Unknown"}
    try:
        for ev in trace.get_events(event_types=["Microsoft-Windows-Kernel-Power/RundownPowerSource/win:Info"]):
            src = ev.get("PowerSource", None)
            if src is None: src = ev.get("AcDcPowerSource", None)
            if src is not None:
                info["power_source"] = "AC" if str(src) == "0" else "DC"
                break
    except Exception as e:
        print(f"[WARNING] power_source: {e}")
    try:
        for ev in trace.get_events(event_types=["Microsoft-Windows-Kernel-Power/RundownEffectiveOverlayPowerScheme/win:Info"]):
            guid = ev.get("EffectivePowerScheme", ev.get("PowerScheme", "Unknown"))
            info["effective_scheme"] = str(guid).lower().strip("{}")
            info["scheme_name"] = GUID_MAPPING.get(info["effective_scheme"], f"Custom ({info['effective_scheme']})")
            break
    except Exception as e:
        print(f"[WARNING] effective_scheme: {e}")
    print(f"[power_state_info] {info}")
    return info

def main():
    ap = argparse.ArgumentParser(description="Standalone power_state_info (speed.exe)")
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
        "power_state_info": extract(trace),
        "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                 "timestamp": datetime.now().isoformat()},
    }
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
