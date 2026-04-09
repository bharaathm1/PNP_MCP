"""
Standalone Containment Analysis Script
========================================
Targeted script: extracts ONLY containment-related data.
Use instead of the full comprehensive analysis when the user asks
about containment, unpark events, or containment policy changes.

PKL output: <etl_basename>_containment.pkl  (same folder as ETL)
Cache check: if the PKL already exists, exits immediately — no re-parse.

Usage:
    speed.exe run standalone_containment.py --etl_file <path>

Output keys in PKL:
    df_containmentunpark       - WPS containment unpark events
    df_containment_policy_change - containment policy change events
    df_containment_breach      - derived breach events (ContainmentEnabled + unpark differential)
"""

import sys
import os
import argparse
import pickle
from datetime import datetime
from pathlib import Path

# SpeedLibs path
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

# ── PKL naming (no timestamp → deterministic cache check) ──────────────────
PKL_SUFFIX = "containment"


def _pkl_path(etl_file_path: str) -> str:
    etl_dir = os.path.dirname(os.path.abspath(etl_file_path))
    basename = os.path.splitext(os.path.basename(etl_file_path))[0]
    return os.path.join(etl_dir, f"{basename}_{PKL_SUFFIX}.pkl")


# ── Extraction functions ───────────────────────────────────────────────────

def extract_wpscontainmentunpark(trace):
    try:
        ts, ce, ccr, beu, aeu, bpu, apu, rtu = [], [], [], [], [], [], [], []
        ev = trace.get_events(
            event_types=["Microsoft-Windows-Kernel-Processor-Power/WpsContainmentUnparkCount/win:Info"])
        for i in ev:
            try:
                ts.append(i["TimeStamp"] / 1000000)
                ce.append(i["ContainmentEnabled"])
                ccr.append(i["ContainmentCrossOverRequired"])
                beu.append(i["BeforeEfficientUnparkCount"])
                aeu.append(i["AfterEfficientUnparkCount"])
                bpu.append(i["BeforePerfUnparkCount"])
                apu.append(i["AfterPerfUnparkCount"])
                rtu.append(i["RawTargetUnparkCount"])
            except Exception:
                pass
        df = pd.DataFrame({"timestamp": ts, "ContainmentEnabled": ce,
                           "ContainmentCrossOverRequired": ccr,
                           "BeforeEfficientUnparkCount": beu, "AfterEfficientUnparkCount": aeu,
                           "BeforePerfUnparkCount": bpu, "AfterPerfUnparkCount": apu,
                           "RawTargetUnparkCount": rtu})
        print(f"[CONTAINMENT] wpscontainmentunpark: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARNING] wpscontainmentunpark error: {e}")
        return pd.DataFrame()


def extract_containment_policy_change(trace):
    try:
        ts, ppm, profileid, value = [], [], [], []
        ev = trace.get_events(
            event_types=["Microsoft-Windows-Kernel-Processor-Power/ContainmentPolicySettingChange/win:Info"])
        for i in ev:
            try:
                ts.append(i["TimeStamp"] / 1000000)
                ppm.append(i["Name"])
                profileid.append(i["ProfileId"])
                value.append(i["Value"])
            except Exception:
                pass
        df = pd.DataFrame({"timestamp": ts, "PPM": ppm, "value": value, "profileid": profileid})
        print(f"[CONTAINMENT] policy_change: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARNING] containment_policy_change error: {e}")
        return pd.DataFrame()


def derive_containment_breach(df_unpark: pd.DataFrame) -> pd.DataFrame:
    """
    Derive breach events: rows where ContainmentEnabled=1 and
    efficient core unpark count changed (After != Before).
    """
    try:
        if df_unpark.empty:
            return pd.DataFrame()
        breach_mask = (
            (df_unpark.get("ContainmentEnabled", pd.Series(dtype=int)) == 1) &
            (df_unpark.get("BeforeEfficientUnparkCount", pd.Series(dtype=int)) !=
             df_unpark.get("AfterEfficientUnparkCount", pd.Series(dtype=int)))
        )
        df_breach = df_unpark[breach_mask].copy()
        df_breach["breach_delta_efficient"] = (
            df_breach["AfterEfficientUnparkCount"] - df_breach["BeforeEfficientUnparkCount"])
        print(f"[CONTAINMENT] breach events derived: {len(df_breach)}")
        return df_breach.reset_index(drop=True)
    except Exception as e:
        print(f"[WARNING] derive_containment_breach error: {e}")
        return pd.DataFrame()


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Standalone Containment Analysis (speed.exe)")
    parser.add_argument("--etl_file", required=True, help="Path to ETL file")
    args = parser.parse_args()

    if not os.path.exists(args.etl_file):
        print(f"[ERROR] ETL file not found: {args.etl_file}")
        sys.exit(1)

    pkl = _pkl_path(args.etl_file)

    # ── Cache check ────────────────────────────────────────────────────────
    if os.path.exists(pkl):
        print(f"[CACHE HIT] PKL already exists, skipping re-analysis.")
        print(f"[OUTPUT_PKL] {pkl}")
        sys.exit(0)

    # ── Load trace ────────────────────────────────────────────────────────
    print(f"[LOAD] Loading trace: {args.etl_file}")
    trace = tracedm.load_trace(etl_file=args.etl_file)
    print(f"[LOAD] OK — {type(trace).__name__}")

    # ── Extract ──────────────────────────────────────────────────────────
    df_unpark    = extract_wpscontainmentunpark(trace)
    df_policy    = extract_containment_policy_change(trace)
    df_breach    = derive_containment_breach(df_unpark)

    results = {
        "df_containmentunpark":        df_unpark,
        "df_containment_policy_change": df_policy,
        "df_containment_breach":        df_breach,
        "meta": {
            "analysis": PKL_SUFFIX,
            "etl_file": args.etl_file,
            "timestamp": datetime.now().isoformat(),
        },
    }

    # ── Save PKL ─────────────────────────────────────────────────────────
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] PKL saved: {pkl}")
    print(f"[OUTPUT_PKL] {pkl}")
    sys.exit(0)


if __name__ == "__main__":
    main()
