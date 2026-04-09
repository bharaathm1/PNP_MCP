"""
Standalone PPM Analysis Script
================================
Targeted script: extracts ONLY PPM (Power Policy Manager) settings data.
Use instead of full comprehensive analysis when the user asks about PPM
settings, PPM validation, or PPM behaviour.

PKL output: <etl_basename>_ppm.pkl  (same folder as ETL)
Cache check: if the PKL already exists, exits immediately — no re-parse.

Usage:
    speed.exe run standalone_ppm.py --etl_file <path> [--ppm_constraints <file>] [--ppm_val_constraints <file>]

Output keys in PKL:
    df_ppm_settings        - baseline PPM settings (ProfileSettingRundown)
    df_ppmsettingschange   - runtime PPM changes (ProfileSettingChange)
    df_PPM_behaviour       - settings vs PPM_constraint.txt
    df_PPM_Validation      - settings vs PPM_VAL_constraints.txt
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
    SPEED_AVAILABLE = False
    sys.exit(1)

PKL_SUFFIX = "ppm"

_CURRENT_DIR = Path(__file__).parent.parent  # ETL_ANALYZER folder
DEFAULT_PPM_CONSTRAINT_FILE    = str(_CURRENT_DIR / "constraints" / "PPM_constraint.txt")
DEFAULT_PPM_VAL_CONSTRAINT_FILE = str(_CURRENT_DIR / "constraints" / "PPM_VAL_constraints.txt")


def _pkl_path(etl_file_path: str) -> str:
    etl_dir  = os.path.dirname(os.path.abspath(etl_file_path))
    basename = os.path.splitext(os.path.basename(etl_file_path))[0]
    return os.path.join(etl_dir, f"{basename}_{PKL_SUFFIX}.pkl")


# ── Helpers ────────────────────────────────────────────────────────────────

def _convert_byte_string_to_decimal(value):
    try:
        if isinstance(value, bytes):
            return int.from_bytes(value[:4] if len(value) >= 4 else value, byteorder="little")
        elif isinstance(value, (int, float)):
            return int(value)
    except Exception:
        pass
    return None


# ── Extraction ─────────────────────────────────────────────────────────────

def extract_ppm_settings_rundown(trace):
    """PPMsettingRundown — baseline settings at trace start."""
    try:
        ts, profileid, ppm, value, vsize, ptype, cls = [], [], [], [], [], [], []
        ev = trace.get_events(
            event_types=["Microsoft-Windows-Kernel-Processor-Power/ProfileSettingRundown/win:Info"])
        for i in ev:
            try:
                ts.append(i["TimeStamp"] / 1000000)
                ppm.append(i["Name"]); profileid.append(i["ProfileId"])
                value.append(i["Value"]); vsize.append(i["ValueSize"])
                ptype.append(i["Type"]); cls.append(i["Class"])
            except Exception:
                pass

        df = pd.DataFrame({"timestamp": ts, "PPM": ppm, "value": value, "profileid": profileid,
                           "ValueSize": vsize, "Type": ptype, "Class": cls})

        if not df.empty:
            # Map profileid to profile name
            ts_p, ids, profiles = [], [], []
            for i in trace.get_events(
                    event_types=["Microsoft-Windows-Kernel-Processor-Power/ProfileRundown/win:Info"]):
                try:
                    ts_p.append(i["TimeStamp"] / 1000000)
                    profiles.append(i["Name"]); ids.append(i["Id"])
                except Exception:
                    pass
            df_p = pd.DataFrame({"Id": ids, "Profile": profiles})
            if not df_p.empty:
                profile_map = df_p.set_index("Id")["Profile"]
                df["profileid"] = df["profileid"].map(profile_map)
                df["value_decimal"] = df["value"].apply(_convert_byte_string_to_decimal)
                df["Type"] = df["Type"].replace({0: "DC", 1: "AC"})
                df["PPM"] = (df["profileid"].astype(str) + "_" + df["PPM"].astype(str) +
                             "_" + df["Type"].astype(str) + "_" + df["Class"].astype(str))
                df.drop(columns=["profileid", "Type", "Class", "ValueSize", "value", "timestamp"],
                        inplace=True)
        print(f"[PPM] settings rundown: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARNING] ppm_settings_rundown error: {e}")
        return pd.DataFrame()


def extract_ppm_settings_change(trace):
    """PPMsettingschange — runtime changes during trace."""
    try:
        ts, ppm, profileid, value = [], [], [], []
        ev = trace.get_events(
            event_types=["Microsoft-Windows-Kernel-Processor-Power/ProfileSettingChange/win:Info"])
        for i in ev:
            try:
                ts.append(i["TimeStamp"] / 1000000)
                ppm.append(i["Name"]); profileid.append(i["ProfileId"]); value.append(i["Value"])
            except Exception:
                pass
        df = pd.DataFrame({"timestamp": ts, "PPM": ppm, "value": value, "profileid": profileid})
        print(f"[PPM] settings change: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARNING] ppm_settings_change error: {e}")
        return pd.DataFrame()


def analyze_ppm_behaviour(ppm_settings_df: pd.DataFrame, constraints_file: str = None) -> pd.DataFrame:
    """Compare PPM settings against a constraints file."""
    try:
        if ppm_settings_df.empty:
            return pd.DataFrame()
        expected = {}
        if constraints_file and os.path.exists(constraints_file):
            with open(constraints_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            expected[parts[0].strip()] = parts[1].strip()
        rows = []
        if "PPM" in ppm_settings_df.columns and "value_decimal" in ppm_settings_df.columns:
            for _, row in ppm_settings_df.iterrows():
                ppm_name = row.get("PPM", "")
                actual   = row.get("value_decimal", None)
                key      = ppm_name.split("_")[1] if "_" in ppm_name else ppm_name
                exp      = expected.get(key)
                rows.append({
                    "ppm_setting": ppm_name, "actual_value": actual,
                    "expected_value": exp,
                    "match":  str(actual) == str(exp) if exp else None,
                    "status": "OK" if not exp or str(actual) == str(exp) else "MISMATCH",
                })
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"[WARNING] analyze_ppm_behaviour error: {e}")
        return pd.DataFrame()


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Standalone PPM Analysis (speed.exe)")
    parser.add_argument("--etl_file",            required=True)
    parser.add_argument("--ppm_constraints",     default=DEFAULT_PPM_CONSTRAINT_FILE)
    parser.add_argument("--ppm_val_constraints", default=DEFAULT_PPM_VAL_CONSTRAINT_FILE)
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

    df_ppm_settings     = extract_ppm_settings_rundown(trace)
    df_ppmsettingschange = extract_ppm_settings_change(trace)
    df_ppm_behaviour    = analyze_ppm_behaviour(df_ppm_settings, args.ppm_constraints)
    df_ppm_validation   = analyze_ppm_behaviour(df_ppm_settings, args.ppm_val_constraints)

    print(f"[PPM] behaviour rows: {len(df_ppm_behaviour)}")
    print(f"[PPM] validation rows: {len(df_ppm_validation)}")

    results = {
        "df_ppm_settings":       df_ppm_settings,
        "df_ppmsettingschange":  df_ppmsettingschange,
        "df_PPM_behaviour":      df_ppm_behaviour,
        "df_PPM_Validation":     df_ppm_validation,
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
