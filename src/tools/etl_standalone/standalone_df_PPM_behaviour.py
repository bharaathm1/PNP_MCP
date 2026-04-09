"""
Standalone: df_PPM_behaviour
==============================
Compares PPM baseline settings against PPM_constraint.txt to identify
settings that deviate from expected values (behaviour validation).
Re-extracts ppm_settings internally so it is fully self-contained.

PKL: <etl_basename>_df_PPM_behaviour.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_df_PPM_behaviour.py --etl_file <path>
                                                 [--ppm_constraints <file>]

PKL keys:
    df_PPM_behaviour — columns: ppm_setting, actual_value, expected_value,
                                match (bool), status (OK / MISMATCH)
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

PKL_SUFFIX = "df_PPM_behaviour"
_CURRENT_DIR = Path(__file__).parent.parent
DEFAULT_CONSTRAINTS = str(_CURRENT_DIR / "constraints" / "PPM_constraint.txt")

def _pkl_path(etl):
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def _bytes_to_decimal(v):
    try:
        if isinstance(v, bytes):
            return int.from_bytes(v[:4] if len(v) >= 4 else v, byteorder="little")
        if isinstance(v, (int, float)):
            return int(v)
    except Exception:
        pass
    return None

def extract_ppm_settings(trace):
    ts, pid, ppm, val, vsize, ptype, cls = [], [], [], [], [], [], []
    for i in trace.get_events(
            event_types=["Microsoft-Windows-Kernel-Processor-Power/ProfileSettingRundown/win:Info"]):
        try:
            ts.append(i["TimeStamp"] / 1000000); ppm.append(i["Name"])
            pid.append(i["ProfileId"]); val.append(i["Value"])
            vsize.append(i["ValueSize"]); ptype.append(i["Type"]); cls.append(i["Class"])
        except Exception:
            pass
    df = pd.DataFrame({"timestamp": ts, "PPM": ppm, "value": val, "profileid": pid,
                       "ValueSize": vsize, "Type": ptype, "Class": cls})
    if not df.empty:
        ts_p, ids, profiles = [], [], []
        for i in trace.get_events(
                event_types=["Microsoft-Windows-Kernel-Processor-Power/ProfileRundown/win:Info"]):
            try:
                profiles.append(i["Name"]); ids.append(i["Id"])
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
    return df

def analyze_behaviour(df_settings, constraints_file):
    expected = {}
    if constraints_file and os.path.exists(constraints_file):
        with open(constraints_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        expected[parts[0].strip()] = parts[1].strip()
    rows = []
    if "PPM" in df_settings.columns and "value_decimal" in df_settings.columns:
        for _, row in df_settings.iterrows():
            name = row.get("PPM", "")
            actual = row.get("value_decimal", None)
            key = name.split("_")[1] if "_" in name else name
            exp = expected.get(key)
            rows.append({"ppm_setting": name, "actual_value": actual, "expected_value": exp,
                         "match": str(actual) == str(exp) if exp else None,
                         "status": "OK" if not exp or str(actual) == str(exp) else "MISMATCH"})
    df = pd.DataFrame(rows)
    print(f"[df_PPM_behaviour] {len(df)} rows, "
          f"{(df['status']=='MISMATCH').sum() if not df.empty else 0} mismatches")
    return df

def main():
    ap = argparse.ArgumentParser(description="Standalone df_PPM_behaviour (speed.exe)")
    ap.add_argument("--etl_file", required=True)
    ap.add_argument("--ppm_constraints", default=DEFAULT_CONSTRAINTS)
    args = ap.parse_args()
    if not os.path.exists(args.etl_file):
        print(f"[ERROR] Not found: {args.etl_file}"); sys.exit(1)
    pkl = _pkl_path(args.etl_file)
    if os.path.exists(pkl):
        print(f"[CACHE HIT] {pkl}"); print(f"[OUTPUT_PKL] {pkl}"); sys.exit(0)
    print(f"[LOAD] {args.etl_file}")
    trace = tracedm.load_trace(etl_file=args.etl_file)
    print(f"[LOAD] OK — {type(trace).__name__}")
    df_settings = extract_ppm_settings(trace)
    df_behaviour = analyze_behaviour(df_settings, args.ppm_constraints)
    results = {
        "df_PPM_behaviour": df_behaviour,
        "df_ppm_settings":  df_settings,
        "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                 "constraints_file": args.ppm_constraints,
                 "timestamp": datetime.now().isoformat()},
    }
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
