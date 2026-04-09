"""
Standalone Hetero-Response & Parking Analysis Script
======================================================
Targeted script: extracts HeteroResponse, HeteroParkingSelection,
and SoftParkSelection events.
Use when the user asks about big.LITTLE / hybrid core parking,
efficiency core vs performance core scheduling, or park/unpark decisions.

PKL output: <etl_basename>_heteroresponse.pkl  (same folder as ETL)
Cache check: if the PKL already exists, exits immediately — no re-parse.

Usage:
    speed.exe run standalone_heteroresponse.py --etl_file <path>

Output keys in PKL:
    df_heteroresponse         - EstimatedUtility / ActualUtility / Decision per interval
    df_heteroparkingselection - total / perf / efficient core unpark counts
    df_softparkselection      - OldPark, NewPark, NewSoftPark bit masks
"""

import sys
import os
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

PKL_SUFFIX = "heteroresponse"


def _pkl_path(etl_file_path: str) -> str:
    etl_dir  = os.path.dirname(os.path.abspath(etl_file_path))
    basename = os.path.splitext(os.path.basename(etl_file_path))[0]
    return os.path.join(etl_dir, f"{basename}_{PKL_SUFFIX}.pkl")


def extract_heteroresponse(trace):
    try:
        ts, et, at, active, decision = [], [], [], [], []
        ev = trace.get_events(
            event_types=["Microsoft-Windows-Kernel-Processor-Power/HeteroResponse/win:Info"])
        for i in ev:
            try:
                ts.append(i["TimeStamp"] / 1000000)
                et.append(max(i["EstimatedUtility"]))
                at.append(max(i["ActualUtility"]))
                active.append(i["ActiveTime"])
                decision.append(i["Decision"])
            except Exception:
                pass
        df = pd.DataFrame({"timestamp": ts, "EstimatedUtility": et, "ActualUtility": at,
                           "ActiveTime": active, "decision": decision})
        print(f"[HETERO] heteroresponse: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARNING] heteroresponse error: {e}")
        return pd.DataFrame()


def extract_heteroparkingselection(trace):
    try:
        ts, ce, total, perf, eff = [], [], [], [], []
        ev = trace.get_events(
            event_types=["Microsoft-Windows-Kernel-Processor-Power/HeteroParkingSelection/win:Info"])
        for i in ev:
            try:
                ts.append(i["TimeStamp"] / 1000000)
                ce.append(i["ContainmentEnabled"])
                total.append(i["TotalCoresUnparkedCount"])
                perf.append(i["PerformanceCoresUnparkedCount"])
                eff.append(i["EfficiencyCoresUnparkedCount"])
            except Exception:
                pass
        df = pd.DataFrame({"timestamp": ts, "ContainmentEnabled": ce,
                           "TotalCoresUnparkedCount": total,
                           "PerformanceCoresUnparkedCount": perf,
                           "EfficiencyCoresUnparkedCount": eff})
        print(f"[HETERO] heteroparkingselection: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARNING] heteroparkingselection error: {e}")
        return pd.DataFrame()


def extract_softparkselection(trace):
    try:
        ts, old_p, new_p, new_sp = [], [], [], []
        ev = trace.get_events(
            event_types=["Microsoft-Windows-Kernel-Processor-Power/SoftParkSelection/win:Info"])
        for i in ev:
            try:
                ts.append(i["TimeStamp"] / 1000000)
                old_p.append(bin(int(i["OldPark"], 16)))
                new_p.append(bin(int(i["NewPark"], 16)))
                new_sp.append(bin(int(i["NewSoftPark"], 16)))
            except Exception:
                pass
        df = pd.DataFrame({"timestamp": ts, "OldPark": old_p,
                           "NewPark": new_p, "NewSoftPark": new_sp})
        print(f"[HETERO] softparkselection: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARNING] softparkselection error: {e}")
        return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description="Standalone Hetero-Response Analysis (speed.exe)")
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
        "df_heteroresponse":        extract_heteroresponse(trace),
        "df_heteroparkingselection": extract_heteroparkingselection(trace),
        "df_softparkselection":     extract_softparkselection(trace),
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
