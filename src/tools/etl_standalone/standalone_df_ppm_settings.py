"""
Standalone: df_ppm_settings
==============================
Extracts PPM (Power Policy Manager) baseline settings from ProfileSettingRundown
events. These are the PPM settings active at trace start, with profile mapping
and decimal value conversion applied.

PKL: <etl_basename>_df_ppm_settings.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_df_ppm_settings.py --etl_file <path>

PKL keys:
    df_ppm_settings — columns: PPM (profile_name_setting_type_class), value_decimal
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

PKL_SUFFIX = "df_ppm_settings"

def _pkl_path(etl):
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def _bytes_to_decimal(value):
    try:
        if isinstance(value, bytes):
            return int.from_bytes(value[:4] if len(value) >= 4 else value, byteorder="little")
        if isinstance(value, (int, float)):
            return int(value)
    except Exception:
        pass
    return None

def extract(trace):
    ts, pid, ppm, val, vsize, ptype, cls = [], [], [], [], [], [], []
    try:
        for i in trace.get_events(
                event_types=["Microsoft-Windows-Kernel-Processor-Power/ProfileSettingRundown/win:Info"]):
            try:
                ts.append(i["TimeStamp"] / 1000000); ppm.append(i["Name"])
                pid.append(i["ProfileId"]); val.append(i["Value"])
                vsize.append(i["ValueSize"]); ptype.append(i["Type"]); cls.append(i["Class"])
            except Exception:
                pass
    except Exception as e:
        print(f"[WARNING] rundown error: {e}")

    df = pd.DataFrame({"timestamp": ts, "PPM": ppm, "value": val, "profileid": pid,
                       "ValueSize": vsize, "Type": ptype, "Class": cls})
    if df.empty:
        return df

    # Profile name mapping
    ts_p, ids, profiles = [], [], []
    try:
        for i in trace.get_events(
                event_types=["Microsoft-Windows-Kernel-Processor-Power/ProfileRundown/win:Info"]):
            try:
                ts_p.append(i["TimeStamp"] / 1000000); profiles.append(i["Name"]); ids.append(i["Id"])
            except Exception:
                pass
    except Exception:
        pass
    df_p = pd.DataFrame({"Id": ids, "Profile": profiles})
    if not df_p.empty:
        pm = df_p.set_index("Id")["Profile"]
        df["profileid"] = df["profileid"].map(pm)
        df["value_decimal"] = df["value"].apply(_bytes_to_decimal)
        df["Type"] = df["Type"].replace({0: "DC", 1: "AC"})
        df["PPM"] = (df["profileid"].astype(str) + "_" + df["PPM"].astype(str) +
                     "_" + df["Type"].astype(str) + "_" + df["Class"].astype(str))
        df.drop(columns=["profileid", "Type", "Class", "ValueSize", "value", "timestamp"],
                inplace=True)
    print(f"[df_ppm_settings] {len(df)} records")
    return df

def main():
    ap = argparse.ArgumentParser(description="Standalone df_ppm_settings (speed.exe)")
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
        "df_ppm_settings": extract(trace),
        "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                 "timestamp": datetime.now().isoformat()},
    }
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
