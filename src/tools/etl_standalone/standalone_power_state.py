"""
Standalone Power State Analysis Script
========================================
Targeted script: extracts power slider state, AC/DC source,
package energy counters, and FG/BG utilization ratio.
Use when the user asks about power mode, AC vs DC, package power,
or foreground/background workload balance.

PKL output: <etl_basename>_power_state.pkl  (same folder as ETL)
Cache check: if the PKL already exists, exits immediately — no re-parse.

Usage:
    speed.exe run standalone_power_state.py --etl_file <path>

Output keys in PKL:
    power_state_info  - dict: power_slider, ac_state, scheme_guid
    df_package_energy - package energy counter (mJ) over time
    df_fg_bg_ratio    - foreground/background utilization ratio over time
    df_epo_changes    - EPO (energy policy object) scheme changes
"""

import sys
import os
import re
import argparse
import pickle
from datetime import datetime
from pathlib import Path

speedlibs_project_path = r"D:\bharath_working_directory\share\agents\SpeedLibs"
if speedlibs_project_path not in sys.path:
    sys.path.insert(0, speedlibs_project_path)

import pandas as pd
import numpy as np

if not hasattr(np, 'int'):
    np.int = int; np.float = float; np.complex = complex; np.bool = bool

try:
    import tracedm
    SPEED_AVAILABLE = True
    print("[OK] SPEED kernel loaded")
except ImportError as e:
    print(f"[ERROR] SPEED kernel not available: {e}")
    sys.exit(1)

PKL_SUFFIX = "power_state"

GUID_MAPPING = {
    "961cc777-2547-4f9d-8174-7d86181b8a7a": "Best Power Efficiency",
    "00000000-0000-0000-0000-000000000000": "Balanced",
    "ded574b5-45a0-4f42-8737-46345c09c238": "Best Performance",
}


def _pkl_path(etl_file_path: str) -> str:
    etl_dir  = os.path.dirname(os.path.abspath(etl_file_path))
    basename = os.path.splitext(os.path.basename(etl_file_path))[0]
    return os.path.join(etl_dir, f"{basename}_{PKL_SUFFIX}.pkl")


def extract_power_state(trace):
    result = {"power_slider": None, "ac_state": None, "scheme_guid": None}
    try:
        for etype in [
            "Microsoft-Windows-UserModePowerService/RundownPowerSource/win:Info",
            "Microsoft-Windows-UserModePowerService/RundownEffectiveOverlayPowerScheme/win:Info",
        ]:
            for ev in trace.get_events(event_types=[etype]):
                if "RundownPowerSource" in ev.get("EVENT_TYPE", ""):
                    try:
                        result["ac_state"] = "AC" if ev["AcOnline"] else "DC"
                    except Exception:
                        pass
                elif "RundownEffectiveOverlay" in ev.get("EVENT_TYPE", ""):
                    try:
                        guid = str(ev["SchemeGuid"]).strip("{}").lower()
                        result["scheme_guid"]  = guid
                        result["power_slider"] = GUID_MAPPING.get(guid, f"Unknown ({guid})")
                    except Exception:
                        pass
    except Exception as e:
        print(f"[WARNING] power_state error: {e}")
    print(f"[POWER] state: {result}")
    return result


def extract_package_energy(trace):
    try:
        ts, cv = [], []
        for i in trace.get_events(
                event_types=["Microsoft-Windows-Kernel-Processor-Power/PackageEnergyCounter/win:Info"]):
            try:
                ts.append(i["TimeStamp"] / 1000000)
                cv.append(i["CounterValue"] / 1000)
            except Exception:
                pass
        df = pd.DataFrame({"timestamp": ts, "Package_Power": cv})
        print(f"[POWER] package_energy: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARNING] package_energy error: {e}")
        return pd.DataFrame()


def extract_fg_bg_ratio(trace):
    try:
        ts, ratio = [], []
        for i in trace.get_events(
                event_types=["Microsoft-Windows-Kernel-Processor-Power/FGBGUtilization/win:Info"]):
            try:
                ts.append(i["TimeStamp"] / 1000000)
                ratio.append(i["FGBGRatio"])
            except Exception:
                pass
        df = pd.DataFrame({"timestamp": ts, "FG_BG_ratio": ratio})
        print(f"[POWER] fg_bg_ratio: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARNING] fg_bg_ratio error: {e}")
        return pd.DataFrame()


def extract_epo_changes(trace):
    try:
        ts, param, value = [], [], []
        for i in trace.get_events(event_types=["EsifUmdf2EtwProvider//win:Info"]):
            try:
                if "Setting power scheme for power source" in i["Message"]:
                    guid_m  = re.search(
                        r"param GUID = ([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12});",
                        i["Message"], re.IGNORECASE)
                    value_m = re.search(r"param Value = (\d+)", i["Message"])
                    if guid_m and value_m:
                        ts.append(i["TimeStamp"] / 1000000)
                        param.append(guid_m.group(1))
                        value.append(value_m.group(1))
            except Exception:
                pass
        df = pd.DataFrame({"timestamp": ts, "param": param, "value": value})
        print(f"[POWER] epo_changes: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARNING] epo_changes error: {e}")
        return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description="Standalone Power State Analysis (speed.exe)")
    parser.add_argument("--etl_file", required=True)
    args = parser.parse_args()

    if not os.path.exists(args.etl_file):
        print(f"[ERROR] ETL file not found: {args.etl_file}")
        sys.exit(1)

    pkl = _pkl_path(args.etl_file)

    if os.path.exists(pkl):
        print(f"[CACHE HIT] PKL already exists, skipping re-analysis.")
        print(f"[OUTPUT_PKL] {pkl}")
        sys.exit(0)

    print(f"[LOAD] Loading trace: {args.etl_file}")
    trace = tracedm.load_trace(etl_file=args.etl_file)
    print(f"[LOAD] OK — {type(trace).__name__}")

    results = {
        "power_state_info":  extract_power_state(trace),
        "df_package_energy": extract_package_energy(trace),
        "df_fg_bg_ratio":    extract_fg_bg_ratio(trace),
        "df_epo_changes":    extract_epo_changes(trace),
        "meta": {
            "analysis": PKL_SUFFIX,
            "etl_file": args.etl_file,
            "timestamp": datetime.now().isoformat(),
        },
    }

    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] PKL saved: {pkl}")
    print(f"[OUTPUT_PKL] {pkl}")
    sys.exit(0)


if __name__ == "__main__":
    main()
