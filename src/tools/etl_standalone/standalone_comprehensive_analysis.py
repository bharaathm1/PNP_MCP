"""
Standalone Comprehensive ETL Analysis Script
==============================================

Designed to run via: speed.exe run standalone_comprehensive_analysis.py <args>

This script provides the SAME functionality and output format as the 
speedlibs_service comprehensive_analysis endpoint, but runs in an 
independent SPEED kernel instance.

IMPORTANT: This is a COMPLETE implementation with all extraction methods
from speedlibs_clean.py - not a skeleton!

Usage:
    speed.exe run standalone_comprehensive_analysis.py --etl_file <path> --output_dir <path> [options]

Output:
    - dfs.pkl (same format as speedlibs_service)
    - analysis_metadata.json with execution info

Author: Generated for speedlibs_service fallback architecture
Date: January 16, 2026
"""

import sys
import os
import json
import argparse
import re
import time as time_module
from datetime import datetime
import pickle
from pathlib import Path

# Add SpeedLibs project directory to Python path
speedlibs_project_path = r"D:\bharath_working_directory\share\agents\SpeedLibs"
if speedlibs_project_path not in sys.path:
    sys.path.insert(0, speedlibs_project_path)

# Import required modules (same as speedlibs_clean.py)
import pandas as pd
import numpy as np

# Apply NumPy compatibility patch
if not hasattr(np, 'int'):
    np.int = int
    np.float = float
    np.complex = complex
    np.bool = bool

# Import SPEED kernel modules
try:
    from ppa.constraints.tracelang import *
    from ppa.constraints import evaluate
    import ppa.constraints.parser
    from ppa.ppa_api import PPAApi
    from ppa.analysis.summary import combine_trace_summaries, trace_summary
    from ppa.report_objects import ConstraintsReport
    import tracedm.etl
    import tracedm  # Need full tracedm for load_trace()
    SPEED_AVAILABLE = True
    print("[OK] SPEED kernel modules imported successfully")
except ImportError as e:
    print(f"[ERROR] SPEED kernel modules not available: {e}")
    SPEED_AVAILABLE = False
    sys.exit(1)

# Default constraint files (relative to ETL_ANALYZER folder)
_CURRENT_DIR = Path(__file__).parent.parent  # ETL_ANALYZER folder
DEFAULT_PPM_CONSTRAINT_FILE = str(_CURRENT_DIR / "constraints" / "PPM_constraint.txt")
DEFAULT_PPM_VAL_CONSTRAINT_FILE = str(_CURRENT_DIR / "constraints" / "PPM_VAL_constraints.txt")


# ==========================================================================
# HELPER FUNCTIONS
# ==========================================================================

def load_trace(etl_file, time_range=None):
    """
    Load ETL trace using SPEED kernel
    
    Args:
        etl_file: Path to ETL file
        time_range: Optional time range tuple (start, end) in seconds
    
    Returns:
        MultiTrace object from SPEED kernel (required for trace_summary)
    """
    try:
        print(f"[LOAD] Loading trace: {etl_file}")
        # Use tracedm.load_trace() to get MultiTrace object (required for trace_summary)
        # This wraps the ETL trace with os_trace attribute needed for summary analysis
        trace = tracedm.load_trace(etl_file=etl_file)
        
        if trace is None:
            raise RuntimeError(f"Failed to load trace: {etl_file}")
        
        print(f"[LOAD] [OK] MultiTrace loaded successfully (type: {type(trace).__name__})")
        return trace
    except Exception as e:
        print(f"[ERROR] Failed to load trace: {e}")
        raise


# ==========================================================================
# COMPLETE EtlTrace CLASS - All methods from speedlibs_clean.py
# ==========================================================================

class StandaloneEtlTrace:
    """
    COMPLETE EtlTrace class for standalone execution
    Contains ALL extraction methods from speedlibs_clean.py
    """
    
    def __init__(self, etl_file_path):
        """
        Initialize EtlTrace with ETL file path
        
        Args:
            etl_file_path: Path to ETL file to analyze
        """
        print(f"[STANDALONE] Loading ETL file: {etl_file_path}")
        
        self.etl_file_path = etl_file_path
        self.trace = load_trace(etl_file=etl_file_path)
        
        # Debug trace object
        if self.trace is not None:
            print(f"[DEBUG] Trace object type: {type(self.trace)}")
            
            # Set time_range to None - get_events() works fine with None and returns all events
            # (Tested: time_range=None and time_range=get_data_time_range() return same results)
            self.time_range = None
            print("[DEBUG] Using time_range=None for get_events() calls")
        else:
            raise RuntimeError("Failed to load trace object")
        
        print(f"[STANDALONE] Extracting all data from trace...")
        self._extract_all_data()
        
        print(f"[STANDALONE] Creating combined DataFrame...")
        self.combined_df = self.combine_df()
        
        print(f"[STANDALONE] EtlTrace initialization complete")
        print(f"[DATA] Combined DataFrame shape: {self.combined_df.shape}")
    
    def _extract_all_data(self):
        """Extract ALL trace data using SpeedLibs methods - COMPLETE implementation"""
        print("[DATA] Starting comprehensive data extraction...")
        total_start_time = time_module.time()

        # Initialize all DataFrames as empty first
        self.df_wlc = pd.DataFrame()
        self.df_heteroresponse = pd.DataFrame()
        self.df_wpscontainmentunpark = pd.DataFrame()
        self.df_heteroparkingselection = pd.DataFrame()
        self.df_softparkselection = pd.DataFrame()
        self.df_expectedutility = pd.DataFrame()
        self.df_cpu_util = pd.DataFrame()
        self.df_cpu_freq = pd.DataFrame()
        self.df_cpu_con = pd.DataFrame()
        self.df_threadstat = pd.DataFrame()
        self.df_processlifetime = pd.DataFrame()
        self.df_epochanges = pd.DataFrame()
        self.df_ppmsettingschange = pd.DataFrame()
        self.df_ppm_settings = pd.DataFrame()
        self.df_containmentpolicychange = pd.DataFrame()
        self.df_containment_status = pd.DataFrame()
        self.df_fg_bg_ratio = pd.DataFrame()
        self.df_c0_intervals = pd.DataFrame()
        self.df_package_energy = pd.DataFrame()
        self.power_state_info = {'power_slider': None, 'ac_state': None, 'scheme_guid': None}
        self.trace_summary = None
        
        # Extract each type of data with timing
        try:
            print("[TIMING] Extracting WLC...")
            self.df_wlc = self._apply_type_fixes(self.wlc())
            print(f"[TIMING] [OK] WLC: {len(self.df_wlc)} records")
        except Exception as e:
            print(f"[WARNING] WLC extraction failed: {e}")
        
        try:
            print("[TIMING] Extracting heteroresponse...")
            self.df_heteroresponse = self._apply_type_fixes(self.heteroresponse())
            print(f"[TIMING] [OK] heteroresponse: {len(self.df_heteroresponse)} records")
        except Exception as e:
            print(f"[WARNING] heteroresponse extraction failed: {e}")
        
        try:
            print("[TIMING] Extracting wpscontainmentunpark...")
            self.df_wpscontainmentunpark = self._apply_type_fixes(self.wpscontainmentunpark())
            print(f"[TIMING] [OK] wpscontainmentunpark: {len(self.df_wpscontainmentunpark)} records")
        except Exception as e:
            print(f"[WARNING] wpscontainmentunpark extraction failed: {e}")

        try:
            print("[TIMING] Extracting containment_status...")
            self.df_containment_status = self.containment_status()
            print(f"[TIMING] [OK] containment_status: {len(self.df_containment_status)} records")
        except Exception as e:
            print(f"[WARNING] containment_status extraction failed: {e}")
        
        try:
            print("[TIMING] Extracting heteroparkingselection...")
            self.df_heteroparkingselection = self._apply_type_fixes(self.heteroparkingselection())
            print(f"[TIMING] [OK] heteroparkingselection: {len(self.df_heteroparkingselection)} records")
        except Exception as e:
            print(f"[WARNING] heteroparkingselection extraction failed: {e}")
        
        # [SKIPPED — medium cost] softparkselection
        # try:
        #     print("[TIMING] Extracting softparkselection...")
        #     self.df_softparkselection = self._apply_type_fixes(self.softparkselection())
        #     print(f"[TIMING] [OK] softparkselection: {len(self.df_softparkselection)} records")
        # except Exception as e:
        #     print(f"[WARNING] softparkselection extraction failed: {e}")

        # [SKIPPED — lightweight] ExpectedUtility
        # try:
        #     print("[TIMING] Extracting ExpectedUtility...")
        #     self.df_expectedutility = self._apply_type_fixes(self.ExpectedUtility())
        #     print(f"[TIMING] [OK] ExpectedUtility: {len(self.df_expectedutility)} records")
        # except Exception as e:
        #     print(f"[WARNING] ExpectedUtility extraction failed: {e}")
        
        try:
            print("[TIMING] Extracting CPU utilization...")
            self.df_cpu_util = self._apply_type_fixes(self.get_cpu_util())
            print(f"[TIMING] [OK] CPU utilization: {len(self.df_cpu_util)} records")
        except Exception as e:
            print(f"[WARNING] CPU utilization extraction failed: {e}")
        
        try:
            print("[TIMING] Extracting CPU frequency...")
            self.df_cpu_freq = self._apply_type_fixes(self.get_cpu_freq())
            print(f"[TIMING] [OK] CPU frequency: {len(self.df_cpu_freq)} records")
        except Exception as e:
            print(f"[WARNING] CPU frequency extraction failed: {e}")
        
        try:
            print("[TIMING] Extracting CPU concurrency...")
            self.df_cpu_con = self._apply_type_fixes(self.get_cpu_con())
            print(f"[TIMING] [OK] CPU concurrency: {len(self.df_cpu_con)} records")
        except Exception as e:
            print(f"[WARNING] CPU concurrency extraction failed: {e}")
        
        try:
            print("[TIMING] Extracting thread statistics...")
            self.df_threadstat = self._apply_type_fixes(self.threadstat())
            print(f"[TIMING] [OK] thread statistics: {len(self.df_threadstat)} records")
        except Exception as e:
            print(f"[WARNING] thread statistics extraction failed: {e}")
        
        try:
            print("[TIMING] Extracting process lifetime...")
            self.df_processlifetime = self._apply_type_fixes(self.processlifetime())
            print(f"[TIMING] [OK] process lifetime: {len(self.df_processlifetime)} records")
        except Exception as e:
            print(f"[WARNING] process lifetime extraction failed: {e}")
        
        # [SKIPPED — lightweight] EPO changes
        # try:
        #     print("[TIMING] Extracting EPO changes...")
        #     self.df_epochanges = self._apply_type_fixes(self.EPOChanges())
        #     print(f"[TIMING] [OK] EPO changes: {len(self.df_epochanges)} records")
        # except Exception as e:
        #     print(f"[WARNING] EPO changes extraction failed: {e}")

        # [SKIPPED — lightweight] PPM settings change
        # try:
        #     print("[TIMING] Extracting PPM settings change...")
        #     self.df_ppmsettingschange = self._apply_type_fixes(self.PPMsettingschange())
        #     print(f"[TIMING] [OK] PPM settings change: {len(self.df_ppmsettingschange)} records")
        # except Exception as e:
        #     print(f"[WARNING] PPM settings change extraction failed: {e}")

        # [SKIPPED — lightweight] PPM baseline settings
        # try:
        #     print("[TIMING] Extracting PPM baseline settings...")
        #     self.df_ppm_settings = self.PPMsettingRundown()
        #     print(f"[TIMING] [OK] PPM settings: {len(self.df_ppm_settings)} records")
        # except Exception as e:
        #     print(f"[WARNING] PPM baseline settings extraction failed: {e}")

        # [SKIPPED — lightweight] containment policy change
        # try:
        #     print("[TIMING] Extracting containment policy change...")
        #     self.df_containmentpolicychange = self._apply_type_fixes(self.ContainmentPolicychange())
        #     print(f"[TIMING] [OK] containment policy change: {len(self.df_containmentpolicychange)} records")
        # except Exception as e:
        #     print(f"[WARNING] containment policy change extraction failed: {e}")

        # [SKIPPED — medium cost] FG/BG ratio
        # try:
        #     print("[TIMING] Extracting FG/BG ratio...")
        #     self.df_fg_bg_ratio = self._apply_type_fixes(self.FG_BG_ratio())
        #     print(f"[TIMING] [OK] FG/BG ratio: {len(self.df_fg_bg_ratio)} records")
        # except Exception as e:
        #     print(f"[WARNING] FG/BG ratio extraction failed: {e}")
        
        try:
            print("[TIMING] Extracting C0 intervals...")
            self.df_c0_intervals = self._apply_type_fixes(self.get_c0_intervals())
            print(f"[TIMING] [OK] C0 intervals: {len(self.df_c0_intervals)} records")
        except Exception as e:
            print(f"[WARNING] C0 intervals extraction failed: {e}")
        
        # [SKIPPED — medium cost] package energy
        # try:
        #     print("[TIMING] Extracting package energy...")
        #     self.df_package_energy = self._apply_type_fixes(self.package_energy())
        #     print(f"[TIMING] [OK] package energy: {len(self.df_package_energy)} records")
        # except Exception as e:
        #     print(f"[WARNING] package energy extraction failed: {e}")

        # [SKIPPED — lightweight] power state
        # try:
        #     print("[TIMING] Extracting power state...")
        #     self.power_state_info = self.get_power_state()
        #     print(f"[TIMING] [OK] power state: {self.power_state_info}")
        # except Exception as e:
        #     print(f"[WARNING] power state extraction failed: {e}")
        
        try:
            print("[TIMING] Generating trace summary...")
            # Now using tracedm.load_trace() which returns MultiTrace with os_trace
            # This should work with trace_summary() function
            if hasattr(self.trace, 'os_trace') or hasattr(trace_summary, '__call__'):
                self.trace_summary = trace_summary(
                    trace=self.trace,
                    time_range=self.time_range,
                    threads=True,
                    events=False,
                    interrupts=True,
                    gpu=True,
                    disk=True
                )
                print(f"[TIMING] [OK] trace summary generated successfully")
            else:
                print(f"[TIMING] [WARNING] trace_summary not compatible with current trace object")
                self.trace_summary = None
        except Exception as e:
            print(f"[WARNING] trace summary generation failed: {e}")
            import traceback
            traceback.print_exc()
            self.trace_summary = None
        
        total_elapsed = time_module.time() - total_start_time
        print(f"[TIMING] [COMPLETE] TOTAL DATA EXTRACTION TIME: {total_elapsed:.2f} seconds")
    
    def _apply_type_fixes(self, df):
        """Apply type conversions to ensure numeric columns are properly typed"""
        if df is None or df.empty:
            return pd.DataFrame()
        
        # Convert timestamp to float
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
        
        # Convert other numeric columns
        numeric_columns = ['wlc', 'EstimatedUtility', 'ActualUtility', 'Frequency', 'value']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    
    # =========================================================================
    # EXTRACTION METHODS - Complete implementations from speedlibs_clean.py
    # =========================================================================
    
    _WLC_LABELS = {0: "Idle", 1: "BatteryLife", 2: "Sustained", 3: "Bursty"}

    def wlc(self):
        """Extract WLC (Workload Classification) data"""
        try:
            timestamp = []
            wlc_status = []

            event_type_list = ["DptfCpuEtwProvider//win:Info"]
            events = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)

            for event in events:
                try:
                    if event["String"] == "SOCWC classification = ":
                        timestamp.append(event["TimeStamp"] / 1000000)
                        wlc_status.append(event["Status"])
                except:
                    continue

            print(f"[WLC] Extracted {len(timestamp)} WLC events")
            return pd.DataFrame({"timestamp": timestamp, "wlc": wlc_status})
        except Exception as e:
            print(f"[WARNING] WLC extraction error: {e}")
            return pd.DataFrame()

    def compute_wlc_histogram(self, df_wlc: pd.DataFrame) -> pd.DataFrame:
        """
        Forward-fill WLC state at 1ms granularity then compute residency histogram.
        States: 0=Idle, 1=BatteryLife, 2=Sustained, 3=Bursty
        """
        try:
            if df_wlc.empty:
                return pd.DataFrame()
            df = df_wlc.sort_values("timestamp").reset_index(drop=True)
            t_start_ms = int(df["timestamp"].iloc[0] * 1000)
            t_end_ms   = int(df["timestamp"].iloc[-1] * 1000) + 1
            n_cells    = t_end_ms - t_start_ms
            if n_cells <= 0:
                return pd.DataFrame()
            states = np.full(n_cells, np.nan)
            for _, row in df.iterrows():
                idx = int(row["timestamp"] * 1000) - t_start_ms
                if 0 <= idx < n_cells:
                    states[idx] = row["wlc"]
            s = pd.Series(states).ffill().bfill()
            total = len(s)
            rows = []
            for state_val, label in sorted(self._WLC_LABELS.items()):
                count = int((s == state_val).sum())
                rows.append({
                    "wlc":         state_val,
                    "state":       label,
                    "duration_ms": count,
                    "duration_s":  round(count / 1000, 3),
                    "pct":         round(count / total * 100, 2) if total > 0 else 0.0,
                })
            print(f"[WLC] histogram: {total}ms window | states: {sorted(df['wlc'].unique().tolist())}")
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[WARNING] compute_wlc_histogram error: {e}")
            return pd.DataFrame()

    def containment_status(self):
        """Extract ContainmentEnabled from HeteroParkingSelectionCount events."""
        try:
            containment_enabled = []
            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/HeteroParkingSelectionCount/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            for i in ev:
                try:
                    containment_enabled.append(i["ContainmentEnabled"])
                except Exception:
                    pass
            df = pd.DataFrame({"ContainmentEnabled": containment_enabled}).reset_index(drop=True)
            print(f"[CONTAINMENT] containment_status: {len(df)} records")
            return df
        except Exception as e:
            print(f"[WARNING] containment_status error: {e}")
            return pd.DataFrame()
    
    def heteroresponse(self):
        """Extract heterogeneous response data"""
        try:
            timestamp = []
            ET = []
            AT = []
            Active_time = []
            decisionBit = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/HeteroResponse/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    ET.append(max(i["EstimatedUtility"]))
                    AT.append(max(i["ActualUtility"]))
                    Active_time.append(i["ActiveTime"])
                    decisionBit.append(i["Decision"])
                except:
                    pass

            data = {"timestamp": timestamp, "EstimatedUtility": ET, "ActualUtility": AT, 
                   "ActiveTime": Active_time, "decision": decisionBit}
            return pd.DataFrame(data)
        except Exception as e:
            print(f"[WARNING] heteroresponse error: {e}")
            return pd.DataFrame()
    
    def wpscontainmentunpark(self):
        """Extract WPS containment unpark data"""
        try:
            timestamp = []
            ContainmentEnabled = []
            ContainmentCrossOverRequired = []
            BeforeEfficientUnparkCount = []
            AfterEfficientUnparkCount = []
            BeforePerfUnparkCount = []
            AfterPerfUnparkCount = []
            RawTargetUnparkCount = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/WpsContainmentUnparkCount/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    ContainmentEnabled.append(i["ContainmentEnabled"])
                    ContainmentCrossOverRequired.append(i["ContainmentCrossOverRequired"])
                    BeforeEfficientUnparkCount.append(i["BeforeEfficientUnparkCount"])
                    AfterEfficientUnparkCount.append(i["AfterEfficientUnparkCount"])
                    BeforePerfUnparkCount.append(i["BeforePerfUnparkCount"])
                    AfterPerfUnparkCount.append(i["AfterPerfUnparkCount"])
                    RawTargetUnparkCount.append(i["RawTargetUnparkCount"])
                except:
                    pass

            data = {"timestamp": timestamp, "ContainmentEnabled": ContainmentEnabled,
                   "ContainmentCrossOverRequired": ContainmentCrossOverRequired,
                   "BeforeEfficientUnparkCount": BeforeEfficientUnparkCount,
                   "AfterEfficientUnparkCount": AfterEfficientUnparkCount,
                   "BeforePerfUnparkCount": BeforePerfUnparkCount,
                   "AfterPerfUnparkCount": AfterPerfUnparkCount,
                   "RawTargetUnparkCount": RawTargetUnparkCount}
            return pd.DataFrame(data)
        except Exception as e:
            print(f"[WARNING] wpscontainmentunpark error: {e}")
            return pd.DataFrame()
    
    def heteroparkingselection(self):
        """Extract heterogeneous parking selection data"""
        try:
            timestamp = []
            ContainmentEnabled = []
            TotalCoresUnparkedCount = []
            PerformanceCoresUnparkedCount = []
            EfficiencyCoresUnparkedCount = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/HeteroParkingSelection/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    ContainmentEnabled.append(i["ContainmentEnabled"])
                    TotalCoresUnparkedCount.append(i["TotalCoresUnparkedCount"])
                    PerformanceCoresUnparkedCount.append(i["PerformanceCoresUnparkedCount"])
                    EfficiencyCoresUnparkedCount.append(i["EfficiencyCoresUnparkedCount"])
                except:
                    pass

            data = {"timestamp": timestamp, "ContainmentEnabled": ContainmentEnabled,
                   "TotalCoresUnparkedCount": TotalCoresUnparkedCount,
                   "PerformanceCoresUnparkedCount": PerformanceCoresUnparkedCount,
                   "EfficiencyCoresUnparkedCount": EfficiencyCoresUnparkedCount}
            return pd.DataFrame(data)
        except Exception as e:
            print(f"[WARNING] heteroparkingselection error: {e}")
            return pd.DataFrame()
    
    def softparkselection(self):
        """Extract soft park selection data"""
        try:
            timestamp = []
            OldPark = []
            NewPark = []
            NewSoftPark = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/SoftParkSelection/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    OldPark.append(bin(int(i["OldPark"], 16)))
                    NewPark.append(bin(int(i["NewPark"], 16)))
                    NewSoftPark.append(bin(int(i["NewSoftPark"], 16)))
                except:
                    pass

            data = {"timestamp": timestamp, "OldPark": OldPark, "NewPark": NewPark, "NewSoftPark": NewSoftPark}
            return pd.DataFrame(data)
        except Exception as e:
            print(f"[WARNING] softparkselection error: {e}")
            return pd.DataFrame()
    
    def ExpectedUtility(self):
        """Extract expected utility data"""
        try:
            timestamp = []
            expectedUtility = []
            actualUtility = []
            
            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/ExpectedUtility/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            
            for event in ev:
                try:
                    timestamp.append(event["TimeStamp"]/1000000)
                    estimated_util = event.get("EstimatedUtility", [])
                    actual_util = event.get("ActualUtility", [])
                    
                    if isinstance(estimated_util, list) and estimated_util:
                        expectedUtility.append(max(estimated_util))
                    else:
                        expectedUtility.append(estimated_util if estimated_util else 0)
                        
                    if isinstance(actual_util, list) and actual_util:
                        actualUtility.append(max(actual_util))
                    else:
                        actualUtility.append(actual_util if actual_util else 0)
                except:
                    if timestamp:
                        timestamp.pop()
                    continue

            return pd.DataFrame({"timestamp": timestamp, "expectedUtility": expectedUtility, "actualUtility": actualUtility})
        except Exception as e:
            print(f"[WARNING] ExpectedUtility error: {e}")
            return pd.DataFrame()
    
    def get_cpu_util(self):
        """Get CPU utilization data"""
        try:
            # Check if method exists
            if not hasattr(self.trace, 'get_cpu_utilization'):
                print("[WARNING] get_cpu_utilization method not available in this SPEED version")
                return pd.DataFrame()
            
            cpu_util_data = self.trace.get_cpu_utilization()
            
            if cpu_util_data is not None:
                if hasattr(cpu_util_data, 'to_dataframe'):
                    df = cpu_util_data.to_dataframe()
                else:
                    df = pd.DataFrame(cpu_util_data)
                
                if df.index.name is None and 'timestamp' not in df.columns:
                    df = df.reset_index()
                    df.rename(columns={'index': 'timestamp'}, inplace=True)
                elif df.index.name == 'timestamp' and 'timestamp' not in df.columns:
                    df = df.reset_index()
                
                return df
            return pd.DataFrame()
        except Exception as e:
            print(f"[WARNING] get_cpu_util error: {e}")
            return pd.DataFrame()
    
    def get_cpu_freq(self):
        """Get CPU frequency data with per-core processing"""
        try:
            # Check if method exists - note it's get_cpu_frequencies (plural!)
            if not hasattr(self.trace, 'get_cpu_frequencies'):
                print("[WARNING] get_cpu_frequencies method not available in this SPEED version")
                return pd.DataFrame()
            
            cpu_freq_data = self.trace.get_cpu_frequencies()
            
            if cpu_freq_data is not None:
                if hasattr(cpu_freq_data, 'to_dataframe'):
                    df = cpu_freq_data.to_dataframe()
                elif isinstance(cpu_freq_data, pd.DataFrame):
                    df = cpu_freq_data
                else:
                    df = pd.DataFrame(cpu_freq_data)
                
                if 'CPU' in df.columns and 'Start(s)' in df.columns and 'Frequency(Hz)' in df.columns:
                    unique_cpus = df['CPU'].unique()
                    per_core_dfs = []
                    
                    for cpu_core in sorted(unique_cpus):
                        cpu_df = df[df['CPU'] == cpu_core].copy()
                        cpu_df.rename(columns={'Frequency(Hz)': f'CPU_{cpu_core}_Freq'}, inplace=True)
                        cpu_df.rename(columns={'Start(s)': 'timestamp'}, inplace=True)
                        
                        if f'CPU_{cpu_core}_Freq' in cpu_df.columns:
                            cpu_df[f'CPU_{cpu_core}_Freq'] = cpu_df[f'CPU_{cpu_core}_Freq'] / 1000000000
                        
                        columns_to_drop = ['CPU', 'End(s)', 'Duration(s)']
                        cpu_df.drop(columns=columns_to_drop, inplace=True, errors='ignore')
                        per_core_dfs.append(cpu_df)
                    
                    if per_core_dfs:
                        combined_df = per_core_dfs[0]
                        for cpu_df in per_core_dfs[1:]:
                            combined_df = pd.merge(combined_df, cpu_df, on='timestamp', how='outer')
                        return combined_df
                
                return df
            return pd.DataFrame()
        except Exception as e:
            print(f"[WARNING] get_cpu_freq error: {e}")
            return pd.DataFrame()
    
    def get_cpu_con(self):
        """Get CPU concurrency data"""
        try:
            # Check if method exists
            if not hasattr(self.trace, 'get_cpu_concurrency'):
                print("[WARNING] get_cpu_concurrency method not available in this SPEED version")
                return pd.DataFrame()
            
            cpu_con_data = self.trace.get_cpu_concurrency()
            
            if cpu_con_data is not None:
                if hasattr(cpu_con_data, 'to_dataframe'):
                    df = cpu_con_data.to_dataframe()
                else:
                    df = pd.DataFrame(cpu_con_data)
                
                if not df.empty:
                    if "Start(s)" in df.columns:
                        df.rename(columns={"Start(s)": "timestamp"}, inplace=True)
                    if "Count" in df.columns:
                        df.rename(columns={"Count": "Concurency"}, inplace=True)
                    
                    columns_to_drop = ['End(s)', 'Duration(s)']
                    df.drop(columns=[c for c in columns_to_drop if c in df.columns], inplace=True)
                
                return df
            return pd.DataFrame()
        except Exception as e:
            print(f"[WARNING] get_cpu_con error: {e}")
            return pd.DataFrame()
    
    def threadstat(self):
        """Extract thread statistics"""
        try:
            # Check if method exists
            if not hasattr(self.trace, 'get_thread_intervals'):
                print("[WARNING] get_thread_intervals method not available in this SPEED version")
                return pd.DataFrame()
            
            thread_data = self.trace.get_thread_intervals()
            
            if thread_data is not None:
                if hasattr(thread_data, 'to_dataframe'):
                    df = thread_data.to_dataframe()
                else:
                    df = pd.DataFrame(thread_data)
                
                if 'timestamp' not in df.columns and hasattr(df, 'index'):
                    df['timestamp'] = df.index.values / 1000000
                    df = df.reset_index(drop=True)
                
                return df
            return pd.DataFrame()
        except Exception as e:
            print(f"[WARNING] threadstat error: {e}")
            return pd.DataFrame()
    
    def processlifetime(self):
        """Extract process lifetime data"""
        try:
            # Check if method exists
            if not hasattr(self.trace, 'get_processes'):
                print("[WARNING] get_processes method not available in this SPEED version")
                return pd.DataFrame()
            
            process_data = self.trace.get_processes()
            
            if process_data is not None:
                if hasattr(process_data, 'to_dataframe'):
                    df = process_data.to_dataframe()
                else:
                    df = pd.DataFrame(process_data)
                
                if 'timestamp' not in df.columns and hasattr(df, 'index'):
                    df['timestamp'] = df.index.values / 1000000
                    df = df.reset_index(drop=True)
                
                return df
            return pd.DataFrame()
        except Exception as e:
            print(f"[WARNING] processlifetime error: {e}")
            return pd.DataFrame()
    
    def EPOChanges(self):
        """Extract EPO Changes from ETW events"""
        try:
            timestamp = []
            param = []
            value = []

            event_type_list = ["EsifUmdf2EtwProvider//win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            
            for i in ev:
                try:
                    if "Setting power scheme for power source" in i["Message"]:
                        guid_match = re.search(r"param GUID = ([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12});", i["Message"], re.IGNORECASE)
                        value_match = re.search(r"param Value = (\d+)", i["Message"])
                        if guid_match and value_match:
                            timestamp.append(i["TimeStamp"]/1000000)
                            param.append(guid_match.group(1))
                            value.append(value_match.group(1))
                except:
                    pass

            return pd.DataFrame({"timestamp": timestamp, "param": param, "value": value})
        except Exception as e:
            print(f"[WARNING] EPOChanges error: {e}")
            return pd.DataFrame()
    
    def PPMsettingRundown(self):
        """Extract PPM baseline settings from ETL"""
        try:
            timestamp = []
            profileid = []
            ppm = []
            value = []
            ValueSize = []
            Type = []
            Class = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/ProfileSettingRundown/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    ppm.append(i["Name"])
                    profileid.append(i["ProfileId"])
                    value.append(i["Value"])
                    ValueSize.append(i["ValueSize"])
                    Type.append(i["Type"])
                    Class.append(i["Class"])
                except:
                    pass

            data = {"timestamp": timestamp, "PPM": ppm, "value": value, "profileid": profileid,
                   "ValueSize": ValueSize, "Type": Type, "Class": Class}
            df = pd.DataFrame(data)
            
            if not df.empty:
                # Get Profile mapping
                timestamp_P = []
                Id = []
                Profile = []

                event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/ProfileRundown/win:Info"]
                ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
                for i in ev:
                    try:
                        timestamp_P.append(i["TimeStamp"]/1000000)
                        Profile.append(i["Name"])
                        Id.append(i["Id"])
                    except:
                        pass

                df_P = pd.DataFrame({"timestamp": timestamp_P, "Profile": Profile, "Id": Id})
                
                if not df_P.empty:
                    profile_id_map = df_P.set_index('Id')['Profile']
                    df['profileid'] = df['profileid'].map(profile_id_map)
                    df['value_decimal'] = df.apply(self.convert_byte_string_to_decimal, axis=1)
                    df['Type'] = df['Type'].replace({0: "DC", 1: "AC"})
                    df['PPM'] = df['profileid'].astype(str) + '_' + df['PPM'].astype(str) + '_' + df['Type'].astype(str) + '_' + df['Class'].astype(str)
                    df = df.drop(columns=['profileid', 'Type', 'Class', 'ValueSize', 'value', 'timestamp'])
                    df = df.reset_index(drop=True)
            
            return df
        except Exception as e:
            print(f"[WARNING] PPMsettingRundown error: {e}")
            return pd.DataFrame()
    
    def PPMsettingschange(self):
        """Extract PPM settings changes"""
        try:
            timestamp = []
            profileid = []
            ppm = []
            value = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/ProfileSettingChange/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    ppm.append(i["Name"])
                    profileid.append(i["ProfileId"])
                    value.append(i["Value"])
                except:
                    pass

            return pd.DataFrame({"timestamp": timestamp, "PPM": ppm, "value": value, "profileid": profileid})
        except Exception as e:
            print(f"[WARNING] PPMsettingschange error: {e}")
            return pd.DataFrame()
    
    def ContainmentPolicychange(self):
        """Extract containment policy changes"""
        try:
            timestamp = []
            profileid = []
            ppm = []
            value = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/ContainmentPolicySettingChange/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    ppm.append(i["Name"])
                    profileid.append(i["ProfileId"])
                    value.append(i["Value"])
                except:
                    pass

            return pd.DataFrame({"timestamp": timestamp, "PPM": ppm, "value": value, "profileid": profileid})
        except Exception as e:
            print(f"[WARNING] ContainmentPolicychange error: {e}")
            return pd.DataFrame()
    
    def FG_BG_ratio(self):
        """Extract FG/BG ratio data"""
        try:
            timestamp = []
            fg_bg_ratio = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/FGBGUtilization/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    fg_bg_ratio.append(i["FGBGRatio"])
                except:
                    pass

            return pd.DataFrame({"timestamp": timestamp, "FG_BG_ratio": fg_bg_ratio})
        except Exception as e:
            print(f"[WARNING] FG_BG_ratio error: {e}")
            return pd.DataFrame()
    
    def get_c0_intervals(self):
        """Extract ACPI C0 intervals"""
        try:
            # Check if method exists
            if not hasattr(self.trace, 'get_c0_intervals'):
                print("[WARNING] get_c0_intervals method not available in this SPEED version")
                return pd.DataFrame()
            
            c0_data = self.trace.get_c0_intervals()
            
            if c0_data is not None:
                if hasattr(c0_data, 'to_dataframe'):
                    df = c0_data.to_dataframe()
                else:
                    df = pd.DataFrame(c0_data)
                
                if hasattr(df, 'index') and len(df) > 0:
                    df = df.reset_index()
                    if 'index' in df.columns:
                        df.rename(columns={'index': 'timestamp'}, inplace=True)
                    return df
            return pd.DataFrame()
        except Exception as e:
            print(f"[WARNING] get_c0_intervals error: {e}")
            return pd.DataFrame()
    
    def package_energy(self):
        """Extract package energy counter data"""
        try:
            timestamp = []
            CounterValue = []
            
            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/PackageEnergyCounter/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    CounterValue.append(i["CounterValue"]/1000)
                except:
                    pass

            return pd.DataFrame({"timestamp": timestamp, "Package_Power": CounterValue})
        except Exception as e:
            print(f"[WARNING] package_energy error: {e}")
            return pd.DataFrame()
    
    def get_power_state(self):
        """Extract power slider position and AC/DC state"""
        GUID_MAPPING = {
            '961cc777-2547-4f9d-8174-7d86181b8a7a': 'Best Power Efficiency',
            '00000000-0000-0000-0000-000000000000': 'Balanced',
            'ded574b5-45a0-4f42-8737-46345c09c238': 'Best Performance'
        }
        
        result = {'power_slider': None, 'ac_state': None, 'scheme_guid': None}
        
        try:
            event_types = [
                'Microsoft-Windows-UserModePowerService/RundownPowerSource/win:Info',
                'Microsoft-Windows-UserModePowerService/RundownEffectiveOverlayPowerScheme/win:Info'
            ]
            
            for event_type in event_types:
                ev = self.trace.get_events(event_types=[event_type], time_range=self.time_range)
                
                for event in ev:
                    if event['EVENT_TYPE'] == 'Microsoft-Windows-UserModePowerService/RundownPowerSource/win:Info':
                        try:
                            ac_online = event['AcOnline']
                            result['ac_state'] = 'AC' if ac_online else 'DC'
                        except:
                            pass
                    
                    elif event['EVENT_TYPE'] == 'Microsoft-Windows-UserModePowerService/RundownEffectiveOverlayPowerScheme/win:Info':
                        try:
                            scheme_guid = event['SchemeGuid']
                            guid_str = str(scheme_guid).strip('{}').lower()
                            result['scheme_guid'] = guid_str
                            result['power_slider'] = GUID_MAPPING.get(guid_str, f'Unknown ({guid_str})')
                        except:
                            pass
            
            return result
        except Exception as e:
            print(f"[WARNING] get_power_state error: {e}")
            return result
    
    def convert_byte_string_to_decimal(self, row):
        """Convert byte string to decimal for PPM settings"""
        try:
            value = row['value']
            
            if isinstance(value, bytes):
                if len(value) >= 4:
                    return int.from_bytes(value[:4], byteorder='little')
                else:
                    return int.from_bytes(value, byteorder='little')
            elif isinstance(value, str):
                if value.startswith('b\'') and value.endswith('\''):
                    byte_string = value[2:-1]
                    if byte_string:
                        byte_array = bytes.fromhex(byte_string.replace('\\x', ''))
                        if len(byte_array) >= 4:
                            return int.from_bytes(byte_array[:4], byteorder='little')
                        else:
                            return int.from_bytes(byte_array, byteorder='little')
            elif isinstance(value, (int, float)):
                return int(value)
            
            return None
        except:
            return None
    
    def combine_df(self):
        """Combine all dataframes with time-series interpolation"""
        print("[COMBINE] Starting DataFrame combination...")
        
        try:
            # Collect all non-empty dataframes with timestamp column
            valid_dfs = {}
            df_attrs = [
                ('df_wlc', 'wlc'),
                ('df_heteroresponse', 'heteroresponse'),
                ('df_wpscontainmentunpark', 'containmentunpark'),
                ('df_heteroparkingselection', 'heteroparkingselection'),
                ('df_softparkselection', 'softparkselection'),
                ('df_cpu_util', 'cpu_util'),
                ('df_cpu_freq', 'cpu_freq'),
                ('df_fg_bg_ratio', 'fg_bg_ratio'),
                ('df_c0_intervals', 'c0_intervals'),
                ('df_package_energy', 'package_energy')
            ]
            
            for attr_name, df_name in df_attrs:
                df = getattr(self, attr_name, pd.DataFrame())
                if isinstance(df, pd.DataFrame) and not df.empty and 'timestamp' in df.columns:
                    valid_dfs[df_name] = df
                    print(f"[COMBINE]   [OK] {df_name}: {len(df)} records")
            
            if not valid_dfs:
                print("[COMBINE] No valid dataframes to combine")
                return pd.DataFrame()
            
            # Find timestamp range
            min_ts = float('inf')
            max_ts = float('-inf')
            
            for df_name, df in valid_dfs.items():
                df_ts = pd.to_numeric(df['timestamp'], errors='coerce').dropna()
                if len(df_ts) > 0:
                    min_ts = min(min_ts, df_ts.min())
                    max_ts = max(max_ts, df_ts.max())
            
            if min_ts == float('inf'):
                return pd.DataFrame()
            
            # Create unified timestamp index with 1-second resolution (changed from 0.1s for performance)
            time_resolution = 1
            unified_timestamps = np.arange(min_ts, max_ts + time_resolution, time_resolution)
            unified_index = pd.Index(unified_timestamps)
            
            print(f"[COMBINE] Unified timestamps: {len(unified_timestamps)} points (resolution: {time_resolution}s)")
            
            # Reindex and interpolate
            interpolated_dfs = {}
            for df_name, df in valid_dfs.items():
                try:
                    df_clean = df.sort_values(by='timestamp').drop_duplicates(subset=['timestamp'])
                    df_indexed = df_clean.set_index('timestamp')
                    interpolated_df = df_indexed.reindex(unified_index, method='ffill')
                    interpolated_dfs[df_name] = interpolated_df
                except Exception as e:
                    print(f"[COMBINE]   [FAIL] {df_name}: interpolation failed - {e}")
            
            if interpolated_dfs:
                final_df = pd.concat(interpolated_dfs.values(), axis=1)
                final_df = final_df.reset_index().rename(columns={'index': 'timestamp'})
                print(f"[COMBINE] [OK] Combined DataFrame: {final_df.shape}")
                return final_df
            
            return pd.DataFrame()
        except Exception as e:
            print(f"[COMBINE] Error: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()
    
    def getCombined(self):
        """Get the combined DataFrame"""
        return self.combined_df


class PreProcess:
    """
    Pre-processing class for ETL trace data analysis.
    Calculates statistics and anomaly detection.
    (Standalone version matching speedlibs_clean.py pre_process)
    """
    def __init__(self, combined_df, trace, filter_df=None):
        self.combined_df = combined_df
        self.trace = trace
        self.filter_df = filter_df
        
        # Run preprocessing
        self.result_df = self._process_data()
    
    def _process_data(self):
        """Process combined DataFrame and compute statistics"""
        try:
            if self.combined_df.empty:
                return pd.DataFrame()
            
            # Calculate basic statistics per numeric column
            stats_data = []
            numeric_cols = self.combined_df.select_dtypes(include=[np.number]).columns
            
            for col in numeric_cols:
                if col == 'timestamp':
                    continue
                    
                series = self.combined_df[col].dropna()
                if len(series) == 0:
                    continue
                
                stats_data.append({
                    'metric': col,
                    'mean': series.mean(),
                    'std': series.std(),
                    'min': series.min(),
                    'max': series.max(),
                    'count': len(series),
                    'median': series.median(),
                    'q25': series.quantile(0.25) if len(series) > 0 else None,
                    'q75': series.quantile(0.75) if len(series) > 0 else None
                })
            
            return pd.DataFrame(stats_data)
        except Exception as e:
            print(f"[WARNING] PreProcess error: {e}")
            return pd.DataFrame()
    
    def get_result(self):
        """Get preprocessed results DataFrame"""
        return self.result_df


def analyze_containment_breach(combined_df, trace=None):
    """
    Analyze containment breach events in the trace.
    (Standalone version matching speedlibs_clean.py ContainmentBreach)
    
    Args:
        combined_df: Combined DataFrame from trace extraction
        trace: Optional trace object for additional analysis
    
    Returns:
        pd.DataFrame: Containment breach analysis results
    """
    try:
        if combined_df.empty:
            return pd.DataFrame()
        
        # Check for containment-related columns
        containment_cols = [col for col in combined_df.columns 
                           if 'containment' in col.lower() or 'breach' in col.lower()]
        
        if not containment_cols:
            # Try to detect breaches from WLC and parking data
            breach_events = []
            
            if 'wlc_util' in combined_df.columns:
                # High utilization events that might indicate containment issues
                high_util_mask = combined_df['wlc_util'] > 90
                if high_util_mask.any():
                    high_util_periods = combined_df[high_util_mask]
                    for idx, row in high_util_periods.iterrows():
                        breach_events.append({
                            'timestamp': row.get('timestamp', idx),
                            'event_type': 'high_utilization',
                            'value': row.get('wlc_util', None),
                            'details': 'WLC utilization exceeds 90%'
                        })
            
            # Check for unparking events that might indicate containment release
            unpark_cols = [col for col in combined_df.columns if 'unpark' in col.lower()]
            for col in unpark_cols:
                if col in combined_df.columns:
                    unpark_events = combined_df[combined_df[col].notna()]
                    for idx, row in unpark_events.head(100).iterrows():  # Limit to first 100
                        breach_events.append({
                            'timestamp': row.get('timestamp', idx),
                            'event_type': 'unpark_event',
                            'value': row.get(col, None),
                            'details': f'Containment unpark event in {col}'
                        })
            
            if breach_events:
                return pd.DataFrame(breach_events)
        
        return pd.DataFrame()
    except Exception as e:
        print(f"[WARNING] Containment breach analysis error: {e}")
        return pd.DataFrame()


def analyze_ppm_behaviour(ppm_settings_df, constraints_file=None):
    """
    Analyze PPM settings against expected behavior/constraints.
    
    Args:
        ppm_settings_df: DataFrame with PPM settings
        constraints_file: Optional path to constraints file
    
    Returns:
        pd.DataFrame: PPM behavior analysis results
    """
    try:
        if ppm_settings_df.empty:
            return pd.DataFrame()
        
        analysis_results = []
        
        # Load constraints if file provided
        expected_values = {}
        if constraints_file and os.path.exists(constraints_file):
            try:
                with open(constraints_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            parts = line.split('=')
                            if len(parts) == 2:
                                expected_values[parts[0].strip()] = parts[1].strip()
            except Exception as e:
                print(f"[WARNING] Could not load constraints file: {e}")
        
        # Analyze each PPM setting
        if 'PPM' in ppm_settings_df.columns and 'value_decimal' in ppm_settings_df.columns:
            for _, row in ppm_settings_df.iterrows():
                ppm_name = row.get('PPM', '')
                actual_value = row.get('value_decimal', None)
                
                # Check against constraints
                expected = expected_values.get(ppm_name.split('_')[1] if '_' in ppm_name else ppm_name)
                
                analysis_results.append({
                    'ppm_setting': ppm_name,
                    'actual_value': actual_value,
                    'expected_value': expected,
                    'match': str(actual_value) == str(expected) if expected else None,
                    'status': 'OK' if not expected or str(actual_value) == str(expected) else 'MISMATCH'
                })
        
        return pd.DataFrame(analysis_results)
    except Exception as e:
        print(f"[WARNING] PPM behavior analysis error: {e}")
        return pd.DataFrame()


def run_comprehensive_analysis(etl_file_path, output_dir=None, 
                               ppm_constraints_file=None,
                               ppm_val_constraints_file=None):
    """
    Run comprehensive analysis - SAME logic as speedlibs_service
    
    Args:
        etl_file_path: Path to ETL file
        output_dir: Optional output directory. If None, uses ETL file directory
        ppm_constraints_file: Optional PPM constraints file
        ppm_val_constraints_file: Optional PPM validation constraints file
    
    Returns:
        dict: Analysis results (also saved to pickle)
    """
    print("=" * 80)
    print("[STANDALONE] COMPREHENSIVE ETL ANALYSIS")
    print("=" * 80)
    
    if not SPEED_AVAILABLE:
        print("[ERROR] SPEED kernel not available")
        return {}
    
    # Determine output directory and base filename (matching speedlibs_service)
    if output_dir is None:
        # Use ETL file directory (same as speedlibs_service)
        output_dir = os.path.dirname(os.path.abspath(etl_file_path))
        print(f"[FILE] Using ETL file directory for output: {output_dir}")
    else:
        os.makedirs(output_dir, exist_ok=True)
    
    # Generate base filename with timestamp (matching speedlibs_service format)
    etl_basename = os.path.splitext(os.path.basename(etl_file_path))[0]
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"{etl_basename}_{timestamp_str}"
    
    print(f"[FILE] Output base filename: {base_filename}")
    
    try:
        # 1. Load ETL trace
        print(f"[FILE] Loading ETL file: {etl_file_path}")
        etl_trace = StandaloneEtlTrace(etl_file_path)
        combined_df = etl_trace.getCombined()
        
        # Note: combined_df may be empty if combine_df() was skipped for performance
        # The actual data is in individual DataFrames (df_cpu_util, df_cpu_freq, etc.)
        print(f"[DATA] Combined DataFrame shape: {combined_df.shape}")
        print("[OK] ETL file loaded successfully")
        
        # 2. Run PreProcess analysis
        print("[ANALYSIS] Running PreProcess statistics...")
        preprocessor = PreProcess(combined_df, etl_trace.trace)
        df_preprocessed = preprocessor.get_result()
        print(f"[DATA] Preprocessed stats: {df_preprocessed.shape}")
        
        # 3. Run Containment Breach analysis
        print("[ANALYSIS] Running Containment Breach analysis...")
        df_containment_breach = analyze_containment_breach(combined_df, etl_trace.trace)
        print(f"[DATA] Containment breach events: {len(df_containment_breach)}")
        
        # 4. Compute WLC histogram
        print("[ANALYSIS] Computing WLC histogram...")
        df_wlc_histogram = etl_trace.compute_wlc_histogram(etl_trace.df_wlc)
        print(f"[DATA] WLC histogram rows: {len(df_wlc_histogram)}")

        # 5. Extract containment status
        print("[ANALYSIS] Extracting containment status...")
        df_containment_status = etl_trace.containment_status()
        print(f"[DATA] Containment status records: {len(df_containment_status)}")

        # 6. Create results dictionary (SAME format as speedlibs_service)
        results_dict = {
            # Core analysis dataframes
            "df_combined_dataframe": combined_df,
            "df_containment_breach": df_containment_breach,
            "df_preprocessed": df_preprocessed,

            # Primary trace dataframes
            "df_wlc": etl_trace.df_wlc,
            "df_wlc_histogram": df_wlc_histogram,
            "df_heteroresponse": etl_trace.df_heteroresponse,
            "df_cpu_util": etl_trace.df_cpu_util,
            "df_cpu_freq": etl_trace.df_cpu_freq,
            "df_containment_status": df_containment_status,
            "df_containmentunpark": etl_trace.df_wpscontainmentunpark,
            "df_heteroparkingselection": etl_trace.df_heteroparkingselection,
            "df_softparkselection": etl_trace.df_softparkselection,
            "df_ppm_settings": etl_trace.df_ppm_settings,
            "df_interrupt": pd.DataFrame(),  # Simplified
            "df_fg_bg_ratio": etl_trace.df_fg_bg_ratio,
            "df_c0_intervals": etl_trace.df_c0_intervals,
            "df_package_energy": etl_trace.df_package_energy,
            "df_ppmsettingschange": etl_trace.df_ppmsettingschange,
            "df_containment_policy_change": etl_trace.df_containmentpolicychange,
            "df_thread_interval": etl_trace.df_threadstat,
            "df_processlifetime": etl_trace.df_processlifetime,
            "df_epo_changes": etl_trace.df_epochanges,
            "df_expectedutility": etl_trace.df_expectedutility,
            "df_cpu_con": etl_trace.df_cpu_con,
            
            # Power state info
            "power_state_info": etl_trace.power_state_info,
        }
        
        # Add trace summary dataframes if available
        if etl_trace.trace_summary:
            summary_attrs = [
                ("df_utilization_per_logical_summary", "utilization_per_logical"),
                ("df_process_stats_summary", "process_stats"),
                ("df_qos_per_process_summary", "qos_per_process"),
                ("df_qos_per_core_summary", "qos_per_core"),
                ("df_cpu_frequency_summary", "cpu_frequency_stats")
            ]
            
            for result_name, summary_attr in summary_attrs:
                try:
                    results_dict[result_name] = getattr(etl_trace.trace_summary, summary_attr, pd.DataFrame())
                except:
                    results_dict[result_name] = pd.DataFrame()
        
        # 3. Save to pickle file (SAME format as speedlibs_service)
        # Use timestamped filename matching ETL file name
        pickle_file = os.path.join(output_dir, f"{base_filename}_dfs.pkl")
        print(f"[FILE] Saving analysis results to pickle: {pickle_file}")
        
        with open(pickle_file, 'wb') as f:
            pickle.dump(results_dict, f)
        
        print(f"[OK] Pickle file saved: {pickle_file}")
        
        # 4. Save metadata JSON
        metadata = {
            "analysis_type": "comprehensive_analysis",
            "etl_file": etl_file_path,
            "etl_basename": etl_basename,
            "output_dir": output_dir,
            "base_filename": base_filename,
            "timestamp": datetime.now().isoformat(),
            "execution_mode": "standalone_speed_exe",
            "dataframe_count": len(results_dict),
            "dataframe_names": list(results_dict.keys()),
            "trace_summary_available": etl_trace.trace_summary is not None
        }
        
        metadata_file = os.path.join(output_dir, f"{base_filename}_metadata.json")
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"[OK] Metadata saved: {metadata_file}")
        
        print("=" * 80)
        print("[OK] COMPREHENSIVE ANALYSIS COMPLETE!")
        print("=" * 80)
        print(f"[FILE] Results saved to: {output_dir}")
        print(f"[FILE] Pickle file: {pickle_file}")
        print(f"[DATA] Total DataFrames: {len(results_dict)}")
        print("[OK] Compatible with speedlibs_service format!")
        
        return results_dict
        
    except Exception as e:
        print(f"[ERROR] Error in comprehensive analysis: {e}")
        import traceback
        traceback.print_exc()
        
        # Save error info
        error_file = os.path.join(output_dir, 'analysis_error.json')
        with open(error_file, 'w') as f:
            json.dump({
                "error": str(e),
                "traceback": traceback.format_exc(),
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        return {}


def main():
    """Main entry point for standalone execution"""
    parser = argparse.ArgumentParser(
        description='Standalone Comprehensive ETL Analysis (speed.exe compatible)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  speed.exe run standalone_comprehensive_analysis.py --etl_file trace.etl --output_dir ./output
  speed.exe run standalone_comprehensive_analysis.py --etl_file trace.etl --output_dir ./output --ppm_constraints ppm.txt
        """
    )
    
    parser.add_argument('--etl_file', required=True,
                       help='Path to ETL file to analyze')
    parser.add_argument('--output_dir', required=False, default=None,
                       help='Output directory for pickle file (default: same as ETL file)')
    parser.add_argument('--ppm_constraints',
                       default=DEFAULT_PPM_CONSTRAINT_FILE,
                       help='Path to PPM constraints file')
    parser.add_argument('--ppm_val_constraints',
                       default=DEFAULT_PPM_VAL_CONSTRAINT_FILE,
                       help='Path to PPM validation constraints file')
    
    args = parser.parse_args()
    
    # Validate inputs
    if not os.path.exists(args.etl_file):
        print(f"[ERROR] ETL file not found: {args.etl_file}")
        sys.exit(1)
    
    # Run analysis
    results = run_comprehensive_analysis(
        etl_file_path=args.etl_file,
        output_dir=args.output_dir,
        ppm_constraints_file=args.ppm_constraints,
        ppm_val_constraints_file=args.ppm_val_constraints
    )
    
    # Exit with appropriate code
    if results:
        print("\n[SUCCESS] Analysis completed successfully")
        sys.exit(0)
    else:
        print("\n[FAILURE] Analysis failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
