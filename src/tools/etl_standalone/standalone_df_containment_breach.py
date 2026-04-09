"""
Standalone: df_containment_breach
====================================
Derives containment breach events from WpsContainmentUnparkCount data.
A breach is defined as a row where ContainmentEnabled=1 AND the efficient
core unpark count changed (After != Before), indicating containment was
unable to hold the core parking decision.

PKL: <etl_basename>_df_containment_breach.pkl  (same folder as ETL)
Cache: skips re-analysis if PKL already exists.

Usage:
    speed.exe run standalone_df_containment_breach.py --etl_file <path>

PKL keys:
    df_containment_breach — subset of df_containmentunpark where breach occurred,
                            plus breach_delta_efficient column
    df_containmentunpark  — full source data (included for reference)
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

PKL_SUFFIX = "df_containment_breach"

def _pkl_path(etl):
    d = os.path.dirname(os.path.abspath(etl))
    b = os.path.splitext(os.path.basename(etl))[0]
    return os.path.join(d, f"{b}_{PKL_SUFFIX}.pkl")

def extract_unpark(trace):
    ts, ce, ccr, beu, aeu, bpu, apu, rtu = [], [], [], [], [], [], [], []
    try:
        for i in trace.get_events(
                event_types=["Microsoft-Windows-Kernel-Processor-Power/WpsContainmentUnparkCount/win:Info"]):
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
    except Exception as e:
        print(f"[WARNING] extract_unpark error: {e}")
    return pd.DataFrame({"timestamp": ts, "ContainmentEnabled": ce,
                         "ContainmentCrossOverRequired": ccr,
                         "BeforeEfficientUnparkCount": beu, "AfterEfficientUnparkCount": aeu,
                         "BeforePerfUnparkCount": bpu, "AfterPerfUnparkCount": apu,
                         "RawTargetUnparkCount": rtu})

def derive_breach(df_unpark):
    if df_unpark.empty:
        return pd.DataFrame()
    mask = (
        (df_unpark.get("ContainmentEnabled", pd.Series(dtype=int)) == 1) &
        (df_unpark.get("BeforeEfficientUnparkCount", pd.Series(dtype=int)) !=
         df_unpark.get("AfterEfficientUnparkCount",  pd.Series(dtype=int)))
    )
    df = df_unpark[mask].copy()
    if not df.empty:
        df["breach_delta_efficient"] = (df["AfterEfficientUnparkCount"] -
                                        df["BeforeEfficientUnparkCount"])
    print(f"[df_containment_breach] {len(df)} breach events from {len(df_unpark)} unpark records")
    return df.reset_index(drop=True)

def main():
    ap = argparse.ArgumentParser(description="Standalone df_containment_breach (speed.exe)")
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
    df_unpark = extract_unpark(trace)
    df_breach = derive_breach(df_unpark)
    results = {
        "df_containment_breach":  df_breach,
        "df_containmentunpark":   df_unpark,
        "meta": {"analysis": PKL_SUFFIX, "etl_file": args.etl_file,
                 "timestamp": datetime.now().isoformat()},
    }
    with open(pkl, "wb") as f:
        pickle.dump(results, f)
    print(f"[OK] {pkl}"); print(f"[OUTPUT_PKL] {pkl}")

if __name__ == "__main__":
    main()
