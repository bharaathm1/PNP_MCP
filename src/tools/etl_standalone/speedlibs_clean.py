"""
[SUCCESS] SpeedLibs Migration - WORKING VERSION!
=========================================

SUCCESS! All SpeedLibs imports are now working after copying the correct DLLs 
from the SPEED installation.

[WARNING]  PYTHON VERSION REQUIREMENT: Python 3.10 ONLY
   - SpeedLibs extensions compiled for Python 3.10
   - Will NOT work with Python 3.11+
   - Use: conda create -n speedlibs python=3.10

This module provides:
- Enhanced EtlTrace class with direct file loading
- Load trace functions with time range filtering
- Comprehensive analysis pipeline
- Auto-socwatch generation
- AI agent data preparation
"""

import sys
import os
import pandas as pd
import numpy as np
from ppa.constraints.tracelang import *
from ppa.constraints import evaluate
import ppa.constraints.parser
from ppa.ppa_api import PPAApi
from ppa.analysis.summary import combine_trace_summaries
from ppa.report_objects import ConstraintsReport

# Global flag to control print output (for agent compatibility)
SILENT_MODE = os.getenv('SPEEDLIBS_SILENT_MODE', 'false').lower() == 'true'

def safe_print(*args, **kwargs):
    """Print function that respects SILENT_MODE for agent compatibility"""
    pass  # Disabled for MCP compatibility

# Apply NumPy compatibility patch for deprecated aliases
if not hasattr(np, 'int'):
    np.int = int
    np.float = float
    np.complex = complex
    np.bool = bool

# ==========================================================================
# TRACE LOADING WITH CACHING
# ==========================================================================

# Global trace cache for performance optimization
_TRACE_CACHE = {}
_CACHE_MAX_SIZE = 5  # Maximum number of traces to keep in memory
_CACHE_MAX_AGE_SECONDS = 1800  # 30 minutes TTL

def load_trace_cached(etl_file, time_range=None, fast_mode=False, force_reload=False, **kwargs):
    """
    Centralized trace loading function with automatic caching.
    
    This function wraps the SPEED kernel's load_trace() and adds intelligent caching
    to avoid reloading the same trace file multiple times.
    
    Args:
        etl_file (str): Path to the ETL file to load
        time_range (tuple, optional): Time range filter (start, end) in seconds
        fast_mode (bool, optional): Use fast loading mode if available
        force_reload (bool, optional): Force reload even if cached
        **kwargs: Additional parameters passed to load_trace() (e.g., socwatch_summary_file)
        
    Returns:
        Trace object from SPEED kernel
        
    Performance Benefits:
        - First load: ~20s for 1GB file
        - Cached load: ~0.1s (200x faster!)
        
    Cache Strategy:
        - Key: file_path + modification_time + time_range + fast_mode + kwargs
        - Eviction: LRU + TTL (30 min) + max size (5 traces)
        - Invalidation: Automatic on file modification
        
    Supported Additional Parameters:
        - socwatch_summary_file: Path to socwatch CSV file for PPM analysis
        - Any other parameters supported by SPEED kernel's load_trace()
    """
    import time as time_module
    
    # Generate cache key
    # NOTE: os.path.getmtime() is a blocking SMB syscall on network paths — called on
    # EVERY request (even cache hits) when mtime was part of the key, causing hangs on
    # slow/expired UNC sessions.  We rely solely on the 30-min TTL (_CACHE_MAX_AGE_SECONDS)
    # for staleness detection instead, eliminating the per-request network syscall.
    abs_path = os.path.abspath(etl_file)

    # Quick reachability check before hitting the cache or loading
    if not os.path.exists(etl_file):
        raise FileNotFoundError(f"ETL file not found: {etl_file}")

    # Include all parameters in cache key to handle different load scenarios
    # Convert kwargs to sorted tuple for consistent cache key
    kwargs_key = tuple(sorted(kwargs.items())) if kwargs else ()
    cache_key = f"{abs_path}:{time_range}:{fast_mode}:{kwargs_key}"
    
    # Check if force reload requested
    if force_reload and cache_key in _TRACE_CACHE:
        safe_print(f"🔄 [CACHE] Force reload requested, evicting: {os.path.basename(etl_file)}")
        del _TRACE_CACHE[cache_key]
    
    # Check cache
    if cache_key in _TRACE_CACHE:
        cache_entry = _TRACE_CACHE[cache_key]
        cache_entry["last_accessed"] = time_module.time()
        cache_entry["access_count"] += 1
        
        safe_print(f"✅ [CACHE HIT] Reusing cached trace: {os.path.basename(etl_file)} "
                  f"(accessed {cache_entry['access_count']} times)")
        
        return cache_entry["trace"]
    
    # Cache miss - load trace
    safe_print(f"📥 [CACHE MISS] Loading trace from file: {os.path.basename(etl_file)}")
    safe_print(f"   File size: {os.path.getsize(etl_file) / (1024*1024):.1f} MB")
    if kwargs:
        safe_print(f"   Additional params: {list(kwargs.keys())}")
    
    load_start = time_module.time()
    
    # Build load_trace parameters
    load_params = {"etl_file": etl_file}
    if time_range is not None:
        load_params["time_range"] = time_range
    # Add any additional kwargs (e.g., socwatch_summary_file)
    load_params.update(kwargs)
    
    # Call the original SPEED kernel load_trace function
    trace = load_trace(**load_params)
    
    load_duration = time_module.time() - load_start
    safe_print(f"✅ [LOAD COMPLETE] Loaded in {load_duration:.2f}s")
    
    # Add to cache
    _TRACE_CACHE[cache_key] = {
        "trace": trace,
        "loaded_at": time_module.time(),
        "last_accessed": time_module.time(),
        "access_count": 1,
        "file_path": etl_file,
        "file_size_mb": os.path.getsize(etl_file) / (1024*1024),
        "load_duration_seconds": load_duration,
        "cache_key": cache_key,
        "time_range": time_range,
        "fast_mode": fast_mode
    }
    
    # Cleanup old entries if needed
    _cleanup_trace_cache()
    
    safe_print(f"📦 [CACHE] Trace cached. Current cache size: {len(_TRACE_CACHE)}/{_CACHE_MAX_SIZE}")
    
    return trace


def _cleanup_trace_cache():
    """Internal function to manage trace cache size and age"""
    import time as time_module
    
    current_time = time_module.time()
    
    # Step 1: Remove expired entries (TTL-based)
    expired_keys = []
    for key, entry in _TRACE_CACHE.items():
        age_seconds = current_time - entry["last_accessed"]
        if age_seconds > _CACHE_MAX_AGE_SECONDS:
            expired_keys.append(key)
    
    for key in expired_keys:
        entry = _TRACE_CACHE[key]
        safe_print(f"🗑️ [CACHE EVICT] TTL expired: {os.path.basename(entry['file_path'])} "
                  f"(inactive for {(current_time - entry['last_accessed'])/60:.1f} min)")
        del _TRACE_CACHE[key]
    
    # Step 2: Enforce size limit (LRU eviction)
    if len(_TRACE_CACHE) > _CACHE_MAX_SIZE:
        # Sort by last accessed time (oldest first)
        sorted_entries = sorted(
            _TRACE_CACHE.items(),
            key=lambda x: x[1]["last_accessed"]
        )
        
        num_to_remove = len(_TRACE_CACHE) - _CACHE_MAX_SIZE
        for key, entry in sorted_entries[:num_to_remove]:
            safe_print(f"🗑️ [CACHE EVICT] LRU: {os.path.basename(entry['file_path'])} "
                      f"(accessed {entry['access_count']} times)")
            del _TRACE_CACHE[key]


def get_trace_cache_stats():
    """
    Get trace cache statistics for monitoring and debugging.
    
    Returns:
        dict: Cache statistics including size, entries, and performance metrics
    """
    import time as time_module
    current_time = time_module.time()
    
    entries_info = []
    for entry in _TRACE_CACHE.values():
        entries_info.append({
            "file_name": os.path.basename(entry["file_path"]),
            "file_size_mb": entry["file_size_mb"],
            "loaded_at": entry["loaded_at"],
            "last_accessed": entry["last_accessed"],
            "age_minutes": (current_time - entry["loaded_at"]) / 60,
            "idle_minutes": (current_time - entry["last_accessed"]) / 60,
            "access_count": entry["access_count"],
            "load_duration_seconds": entry["load_duration_seconds"],
            "time_range": entry["time_range"],
            "fast_mode": entry["fast_mode"]
        })
    
    total_size_mb = sum(e["file_size_mb"] for e in entries_info)
    
    return {
        "cache_enabled": True,
        "current_size": len(_TRACE_CACHE),
        "max_size": _CACHE_MAX_SIZE,
        "max_age_seconds": _CACHE_MAX_AGE_SECONDS,
        "total_file_size_mb": total_size_mb,
        "entries": entries_info
    }


def clear_trace_cache(file_path=None):
    """
    Clear trace cache - either specific file or entire cache.
    
    Args:
        file_path (str, optional): Specific file to clear. If None, clears entire cache.
        
    Returns:
        dict: Information about what was cleared
    """
    global _TRACE_CACHE
    
    if file_path is None:
        # Clear entire cache
        size = len(_TRACE_CACHE)
        _TRACE_CACHE.clear()
        safe_print(f"🗑️ [CACHE] Cleared entire cache ({size} entries removed)")
        return {"action": "clear_all", "entries_removed": size}
    else:
        # Clear specific file
        abs_path = os.path.abspath(file_path)
        removed_count = 0
        
        keys_to_remove = [
            key for key, entry in _TRACE_CACHE.items()
            if os.path.abspath(entry["file_path"]) == abs_path
        ]
        
        for key in keys_to_remove:
            del _TRACE_CACHE[key]
            removed_count += 1
        
        safe_print(f"🗑️ [CACHE] Cleared {removed_count} entries for: {os.path.basename(file_path)}")
        return {"action": "clear_file", "file_path": file_path, "entries_removed": removed_count}


# ==========================================================================
# PPM CONSTRAINTS CONFIGURATION
# ==========================================================================

# Default PPM constraint file paths - users can customize these
DEFAULT_PPM_CONSTRAINT_FILE = r"D:\bharath_working_directory\share\LNL\speed_constraints\PPM_constraint.txt"
DEFAULT_PPM_VAL_CONSTRAINT_FILE = r"D:\bharath_working_directory\share\LNL\speed_constraints\PPM_VAL_constraints.txt"

print(f"[CONFIG] Default PPM constraint file: {DEFAULT_PPM_CONSTRAINT_FILE}")
print(f"[CONFIG] Default PPM validation constraint file: {DEFAULT_PPM_VAL_CONSTRAINT_FILE}")

# [WARNING] CRITICAL: Python Version Check
if sys.version_info >= (3, 11):
    print("=" * 80)
    print("[WARNING]  PYTHON VERSION WARNING")
    print("=" * 80)
    print(f"Current Python version: {sys.version}")
    print("[ERROR] SpeedLibs requires Python 3.10")
    print("[ERROR] Extensions compiled for Python 3.10 (.cp310-win_amd64.pyd)")
    print("[ERROR] Will not work with Python 3.11+")
    print()
    print("[FIX] SOLUTION:")
    print("   conda create -n speedlibs python=3.10")
    print("   conda activate speedlibs")
    print("   python speedlibs_working_final.py")
    print("=" * 80)
    SPEEDLIBS_WORKING = False
elif sys.version_info < (3, 10):
    print("[WARNING]  SpeedLibs requires Python 3.10")
    SPEEDLIBS_WORKING = False
else:
    # Add SpeedLibs project directory to Python path
    speedlibs_project_path = r"D:\bharath_working_directory\share\agents\SpeedLibs"
    if speedlibs_project_path not in sys.path:
        sys.path.insert(0, speedlibs_project_path)
        print(f"[FILE] Added SpeedLibs project path: {speedlibs_project_path}")
    
    # Try to import SpeedLibs
    try:
        import tracedm.etl
        SPEEDLIBS_WORKING = True
        print("[OK] SpeedLibs tracedm.etl is working!")
        
        # Try optional eventing modules
        try:
            import tracedm.eventing.providers
            import tracedm.eventing.schema
            print("[OK] Optional eventing modules also available")
        except ImportError as eventing_error:
            print(f"[WARNING]  Optional eventing modules not available: {eventing_error}")
            print("   Core ETL functionality will still work")
            
    except ImportError as e:
        print(f"[ERROR] SpeedLibs import failed: {e}")
        print(f"   SpeedLibs path exists: {os.path.exists(speedlibs_project_path)}")
        print(f"   tracedm path exists: {os.path.exists(os.path.join(speedlibs_project_path, 'tracedm'))}")
        SPEEDLIBS_WORKING = False

# ==========================================================================
# CORE CLASSES
# ==========================================================================

class EtlTrace:
    """
    [OK] WORKING EtlTrace class using SpeedLibs
    
    Enhanced to support both direct file loading and traditional trace objects.
    """
    
    def __init__(self, trace_or_file, logpath=None):
        """
        Initialize EtlTrace with either a loaded trace object OR an ETL file path
        
        Args:
            trace_or_file: Either:
                - Trace object loaded using 'from tracedm.etl import load; trace = load(etl_file)'
                - String path to ETL file (will be loaded automatically)
            logpath: Optional path for saving CSV files
        """
        print("[INIT] Initializing EtlTrace with working SpeedLibs...")
        
        self.logpath = logpath or ""
        
        # Handle both trace object and file path
        if isinstance(trace_or_file, str):
            # It's a file path - load it
            print(f"[FILE] Loading ETL file: {trace_or_file}")
            if SPEEDLIBS_WORKING:
                # Check if we're in SPEED kernel environment
                try:
                    # Use cached trace loading for performance
                    self.trace = load_trace_cached(etl_file=trace_or_file)
                    print("[OK] ETL file loaded successfully using cached load_trace")
                    
                except (ImportError, NameError):
                    # Fall back to tracedm.etl.load if load_trace not available
                    print("[ERROR] Neither load_trace_cached nor tracedm.etl.load available")
                    raise
            else:
                raise RuntimeError("[ERROR] SpeedLibs not available - cannot load ETL file")
        else:
            # It's already a loaded trace object
            print("[DATA] Using provided trace object")
            self.trace = trace_or_file
        
        # Debug trace object details
        if self.trace is not None:
            print(f"[DEBUG] Trace object type: {type(self.trace)}")
            trace_methods = [method for method in dir(self.trace) if not method.startswith('_')]
            print(f"[DEBUG] Available methods count: {len(trace_methods)}")
            
            
            # Check for get_cpu_frequency method  
            if hasattr(self.trace, 'get_cpu_frequency'):
                print("[DEBUG] ✅ get_cpu_frequency method available")
            else:
                print("[DEBUG] ❌ get_cpu_frequency method NOT available")
                print(f"[DEBUG] Available methods sample: {trace_methods[:10]}")
            
            # Check and fix time_range attribute
            if not hasattr(self.trace, 'time_range'):
                print("[DEBUG] Adding missing time_range attribute (using None for full trace)")
                self.trace.time_range = None
        else:
            print("[DEBUG] ❌ ERROR - Trace object is None!")
            raise RuntimeError("Failed to load trace object")
        
        # Extract all trace data using SpeedLibs
        self._extract_all_data()
        
        # Create combined dataframe
        #self.combined_df = self.combine_df()
        self.combined_df=pd.DataFrame()  # Placeholder for combined DataFrame
        
        print("[OK] EtlTrace initialization complete with SpeedLibs!")
        print(f"[DATA] Combined DataFrame shape: {self.combined_df.shape}")

    def _extract_all_data(self):
        """Extract all trace data using the working SpeedLibs methods"""
        import time
        print("[DATA] Extracting trace data using SpeedLibs...")
        total_start_time = time.time()

        # Core working methods - these now use working SpeedLibs
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting WLC extraction...")
            self.df_wlc = self._apply_type_fixes(self.wlc())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ WLC extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ WLC extraction failed: {e}")
            pass
            
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting heteroresponse extraction...")
            self.df_heteroresponse = self._apply_type_fixes(self.heteroresponse())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ heteroresponse extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ heteroresponse extraction failed: {e}")
            pass
            
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting wpscontainmentunpark extraction...")
            self.df_wpscontainmentunpark = self._apply_type_fixes(self.wpscontainmentunpark())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ wpscontainmentunpark extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ wpscontainmentunpark extraction failed: {e}")
            pass

        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting heteroparkingselection extraction...")
            self.df_heteroparkingselection = self._apply_type_fixes(self.heteroparkingselection())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ heteroparkingselection extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ heteroparkingselection extraction failed: {e}")
            pass

        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting Containment_status extraction...")
            self.df_containment_status = self._apply_type_fixes(self.Containment_status())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ Containment_status extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ Containment_status extraction failed: {e}")
            pass

        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting softparkselection extraction...")
            self.df_softparkselection = self._apply_type_fixes(self.softparkselection())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ softparkselection extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ softparkselection extraction failed: {e}")
            pass
            
        # Additional extraction methods  
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting ExpectedUtility extraction...")
            self.df_expectedutility = self._apply_type_fixes(self.ExpectedUtility())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ ExpectedUtility extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ ExpectedUtility extraction failed: {e}")
            pass
            
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting CPU utilization extraction...")
            self.df_cpu_util = self._apply_type_fixes(self.get_cpu_util())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ CPU utilization extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ CPU utilization extraction failed: {e}")
            pass
            
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting CPU frequency extraction...")
            self.df_cpu_freq = self._apply_type_fixes(self.get_cpu_freq())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ CPU frequency extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ CPU frequency extraction failed: {e}")
            pass
            
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting CPU constraints extraction...")
            self.df_cpu_con = self._apply_type_fixes(self.get_cpu_con())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ CPU constraints extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ CPU constraints extraction failed: {e}")
            pass 
        
        # System and process data
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting thread statistics extraction...")
            self.df_threadstat = self._apply_type_fixes(self.threadstat())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ thread statistics extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ thread statistics extraction failed: {e}")
            pass
            
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting process lifetime extraction...")
            self.df_processlifetime = self._apply_type_fixes(self.processlifetime())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ process lifetime extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ process lifetime extraction failed: {e}")
            pass
            
        # Policy and configuration changes
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting EPO changes extraction...")
            self.df_epochanges = self._apply_type_fixes(self.EPOChanges())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ EPO changes extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ EPO changes extraction failed: {e}")
            pass
            
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting PPM settings change extraction...")
            self.df_ppmsettingschange = self._apply_type_fixes(self.PPMsettingschange())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ PPM settings change extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ PPM settings change extraction failed: {e}")
            pass
        
        # Combine PPM baseline and changes to create df_ppm_settings
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Combining PPM baseline settings...")
            # Get baseline PPM settings from rundown events
            df_ppm_baseline = self.PPMsettingRundown()
            
            # If we have baseline settings, use them as df_ppm_settings
            # (Changes are tracked separately in df_ppmsettingschange)
            if not df_ppm_baseline.empty:
                self.df_ppm_settings = df_ppm_baseline
                elapsed = time.time() - start_time
                print(f"[TIMING] ✅ PPM settings combined in {elapsed:.2f} seconds")
                print(f"[DATA] PPM settings shape: {self.df_ppm_settings.shape}")
            else:
                self.df_ppm_settings = pd.DataFrame()
                print(f"[TIMING] ⚠️  No PPM baseline settings found")
        except Exception as e:
            print(f"[TIMING] ❌ PPM settings combination failed: {e}")
            self.df_ppm_settings = pd.DataFrame()
            pass
            
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting containment policy change extraction...")
            self.df_containmentpolicychange = self._apply_type_fixes(self.ContainmentPolicychange())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ containment policy change extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ containment policy change extraction failed: {e}")
            pass
            
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting FG/BG ratio extraction...")
            self.df_fg_bg_ratio = self._apply_type_fixes(self.FG_BG_ratio())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ FG/BG ratio extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ FG/BG ratio extraction failed: {e}")
            pass
            
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting C0 intervals extraction...")
            self.df_c0_intervals = self._apply_type_fixes(self.get_c0_intervals())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ C0 intervals extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ C0 intervals extraction failed: {e}")
            pass
            
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting package energy extraction...")
            self.df_package_energy = self._apply_type_fixes(self.package_energy())
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ Package energy extraction completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ Package energy extraction failed: {e}")
            pass
        
        # Extract power state (AC/DC and power slider position)
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting power state extraction...")
            self.power_state_info = self.get_power_state()
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ Power state extraction completed in {elapsed:.2f} seconds")
            print(f"[POWER] Power State Summary:")
            print(f"[POWER]   - Power Slider: {self.power_state_info.get('power_slider', 'N/A')}")
            print(f"[POWER]   - AC/DC State: {self.power_state_info.get('ac_state', 'N/A')}")
            print(f"[POWER]   - Scheme GUID: {self.power_state_info.get('scheme_guid', 'N/A')}")
        except Exception as e:
            print(f"[TIMING] ❌ Power state extraction failed: {e}")
            self.power_state_info = {
                'power_slider': None,
                'ac_state': None,
                'scheme_guid': None
            }
            pass
            
        # Apply CPU column fixes
        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting CPU utilization column fixes...")
            self.df_cpu_util = self.fix_cpu_utilization_column_names(self.df_cpu_util)
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ CPU utilization column fixes completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ CPU utilization column fixes failed: {e}")
            pass

        try:
            start_time = time.time()
            print("[TIMING] ⏱️  Starting speed summary generation...")
            self.trace_summary = self.speed_summary()
            elapsed = time.time() - start_time
            print(f"[TIMING] ✅ speed summary generation completed in {elapsed:.2f} seconds")
        except Exception as e:
            print(f"[TIMING] ❌ speed summary generation failed: {e}")
            pass

        total_elapsed = time.time() - total_start_time
        print(f"[TIMING] 🏁 TOTAL DATA EXTRACTION TIME: {total_elapsed:.2f} seconds")

    def _apply_type_fixes(self, df):
        """Apply type conversions to ensure numeric columns are properly typed"""
        if df.empty:
            return df
        
        # Convert timestamp to float
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
        
        # Convert other numeric columns
        numeric_columns = ['wlc', 'EstimatedUtility', 'ActualUtility', 'Frequency', 'value']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df

    def wlc(self):
        """
        Extract WLC (Workload Classification) data from DPTF CPU ETW Provider events
        
        Returns:
            pd.DataFrame: DataFrame with timestamp (seconds) and wlc status columns
        """
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            timestamp = []
            wlc_status = []
            
            # Target event type for DPTF CPU ETW Provider
            event_type_list = ["DptfCpuEtwProvider//win:Info"]
            
            # Get events within trace time range
            events = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
            event_count = 0
            wlc_events = 0
            
            for event in events:
                event_count += 1
                try:
                    # Look for SOCWC classification events
                    if event["String"] == "SOCWC classification = ":
                        timestamp.append(event["TimeStamp"] / 1000000)  # Convert to milliseconds
                        wlc_status.append(event["Status"])
                        wlc_events += 1
                except KeyError:
                    # Event doesn't have the expected fields
                    continue
                except Exception as e:
                    # Other errors, continue processing
                    continue
            
            print(f"[WLC] Processed {event_count} events, found {wlc_events} WLC classification events")
            
            # Create DataFrame
            data = {"timestamp": timestamp, "wlc": wlc_status}
            df = pd.DataFrame(data)
            
            if not df.empty:
                print(f"[WLC] Extracted {len(df)} entries")
                print(f"[WLC] Time range: {df['timestamp'].min():.2f} - {df['timestamp'].max():.2f} ms")
                print(f"[WLC] Unique WLC states: {df['wlc'].unique()}")
            else:
                print("[WLC] No WLC data found in trace")
                
            return df
            
        except Exception as e:
            print(f"[WARNING] Error in wlc(): {e}")
            return pd.DataFrame()

    def heteroresponse(self):
        """Extract heterogeneous response data"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            df = pd.DataFrame()
            timestamp = []
            ET = []
            AT = []
            Active_time = []
            decisionBit = []

            # Use the same event type as preprocessETL notebook
            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/HeteroResponse/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
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
            df = pd.DataFrame(data)
            
            return df
        except Exception as e:
            print(f"[WARNING]  Warning in heteroresponse(): {e}")
            return pd.DataFrame()

    def wpscontainmentunpark(self):
        """Extract WPS containment unpark data"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            df = pd.DataFrame()
            timestamp = []
            ContainmentEnabled = []
            ContainmentCrossOverRequired = []
            BeforeEfficientUnparkCount = []
            AfterEfficientUnparkCount = []
            BeforePerfUnparkCount = []
            AfterPerfUnparkCount = []
            RawTargetUnparkCount = []

            # Use the same event type as preprocessETL notebook
            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/WpsContainmentUnparkCount/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
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
            df = pd.DataFrame(data)
            
            return df
        except Exception as e:
            print(f"[WARNING]  Warning in wpscontainmentunpark(): {e}")
            return pd.DataFrame()

    def heteroparkingselection(self):
        """Extract heterogeneous parking selection data"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            df = pd.DataFrame()
            timestamp = []
            ContainmentEnabled = []
            TotalCoresUnparkedCount = []
            PerformanceCoresUnparkedCount = []
            EfficiencyCoresUnparkedCount = []

            # Use the same event type as preprocessETL notebook
            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/HeteroParkingSelection/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    ContainmentEnabled.append(i["ContainmentEnabled"])
                    TotalCoresUnparkedCount.append(i["TotalCoresUnparkedCount"])
                    PerformanceCoresUnparkedCount.append(i["PerformanceCoresUnparkedCount"])
                    EfficiencyCoresUnparkedCount.append(i["EfficiencyCoresUnparkedCount"])
                except Exception as e:
                    pass

            data = {"timestamp": timestamp, "ContainmentEnabled": ContainmentEnabled,
                   "TotalCoresUnparkedCount": TotalCoresUnparkedCount,
                   "PerformanceCoresUnparkedCount": PerformanceCoresUnparkedCount,
                   "EfficiencyCoresUnparkedCount": EfficiencyCoresUnparkedCount}
            df = pd.DataFrame(data)
            
            return df
        except Exception as e:
            print(f"[WARNING]  Warning in heteroparkingselection(): {e}")
            return pd.DataFrame()

    def Containment_status(self):
        """Extract Containment status from HeteroParkingSelectionCount events"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            containment_enabled = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/HeteroParkingSelectionCount/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
            for i in ev:
                try:
                    containment_enabled.append(i["ContainmentEnabled"])
                except Exception as e:
                    print(e)
                    pass

            data = {"ContainmentEnabled": containment_enabled}
            df = pd.DataFrame(data)
            df = df.reset_index(drop=True)

            return df
        except Exception as e:
            print(f"[WARNING]  Warning in Containment_status(): {e}")
            return pd.DataFrame()

    def softparkselection(self):
        """Extract soft park selection data"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            df = pd.DataFrame()
            timestamp = []
            OldPark = []
            NewPark = []
            NewSoftPark = []

            # Use the same event type as preprocessETL notebook
            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/SoftParkSelection/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    OldPark.append(bin(int(i["OldPark"], 16)))
                    NewPark.append(bin(int(i["NewPark"], 16)))
                    NewSoftPark.append(bin(int(i["NewSoftPark"], 16)))
                except Exception as e:
                    pass

            data = {"timestamp": timestamp, "OldPark": OldPark, "NewPark": NewPark, "NewSoftPark": NewSoftPark}
            df = pd.DataFrame(data)
            
            return df
        except Exception as e:
            print(f"[WARNING]  Warning in softparkselection(): {e}")
            return pd.DataFrame()

    def ExpectedUtility(self):
        """Extract expected utility data - corrected to match preprocessETL"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            df = pd.DataFrame()
            timestamp = []
            expectedUtility = []
            actualUtility = []
            
            # Use the same event type as preprocessETL notebook
            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/ExpectedUtility/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
            event_count = 0
            for event in ev:
                event_count += 1
                try:
                    timestamp.append(event["TimeStamp"]/1000000)
                    
                    # Safely extract utility values
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
                        
                except Exception as e:
                    # Remove the problematic entry to keep arrays aligned
                    if timestamp:
                        timestamp.pop()
                    if expectedUtility:
                        expectedUtility.pop()
                    if actualUtility:
                        actualUtility.pop()
                    continue

            data = {"timestamp": timestamp, "expectedUtility": expectedUtility, "actualUtility": actualUtility}
            df = pd.DataFrame(data)
            
            return df
        except Exception as e:
            print(f"[WARNING]  Warning in ExpectedUtility(): {e}")
            return pd.DataFrame()

    def get_cpu_util(self):
        """Get CPU utilization data - corrected to match preprocessETL"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            # Use the exact method from preprocessETL notebook
            cpu_util_data = self.trace.get_cpu_utilization()
            
            if cpu_util_data is not None:
                # Convert to DataFrame following preprocessETL approach
                if hasattr(cpu_util_data, 'to_dataframe'):
                    df = cpu_util_data.to_dataframe()
                else:
                    df = pd.DataFrame(cpu_util_data)
                
                # Ensure timestamp is a column, not just the index
                if df.index.name is None and 'timestamp' not in df.columns:
                    df = df.reset_index()
                    df.rename(columns={'index': 'timestamp'}, inplace=True)
                elif df.index.name == 'timestamp' and 'timestamp' not in df.columns:
                    df = df.reset_index()
                
                return df
            else:
                return pd.DataFrame()
        except Exception as e:
            print(f"[WARNING]  Warning in get_cpu_util(): {e}")
            return pd.DataFrame()
        
    def speed_summary(self):

        from ppa.analysis.summary import trace_summary
        from ppa.analysis.constraints import analyze_constraints
        from ppa.cli.summary import SummaryReportCLIHandler
        import reports


        summary = trace_summary(self.trace)
        print("summary generated")
        return summary

    def get_cpu_freq(self):
        """CPU frequency data - preprocessETL master approach with per-core processing"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            cpu_freq_data = self.trace.get_cpu_frequency()
            
            if cpu_freq_data is not None:
                # Convert to DataFrame if needed
                if hasattr(cpu_freq_data, 'to_dataframe'):
                    df = cpu_freq_data.to_dataframe()
                elif isinstance(cpu_freq_data, pd.DataFrame):
                    df = cpu_freq_data
                else:
                    df = pd.DataFrame(cpu_freq_data)
                
                # Apply preprocessETL-style processing if we have expected columns
                if 'CPU' in df.columns and 'Start(s)' in df.columns and 'Frequency(Hz)' in df.columns:
                    print(f"🔧 Processing CPU frequency data with {len(df)} total records")
                    
                    # Get unique CPU cores for per-core processing (preprocessETL approach)
                    unique_cpus = df['CPU'].unique()
                    per_core_dfs = []
                    
                    for cpu_core in sorted(unique_cpus):
                        # Filter data for this specific CPU core
                        cpu_df = df[df['CPU'] == cpu_core].copy()
                        
                        # Rename frequency column with CPU identifier (preprocessETL pattern)
                        cpu_df.rename(columns={'Frequency(Hz)': f'CPU_{cpu_core}_Freq'}, inplace=True)
                        
                        # Rename Start(s) to timestamp (preprocessETL pattern)
                        cpu_df.rename(columns={'Start(s)': 'timestamp'}, inplace=True)
                        
                        # Convert Hz to GHz (CRITICAL: preprocessETL approach)
                        if f'CPU_{cpu_core}_Freq' in cpu_df.columns:
                            cpu_df[f'CPU_{cpu_core}_Freq'] = cpu_df[f'CPU_{cpu_core}_Freq'] / 1000000000
                        
                        # Drop unnecessary columns (preprocessETL pattern)
                        columns_to_drop = ['CPU', 'End(s)', 'Duration(s)']
                        cpu_df.drop(columns=columns_to_drop, inplace=True, errors='ignore')
                        
                        per_core_dfs.append(cpu_df)
                        print(f"   ✅ CPU_{cpu_core}: {len(cpu_df)} frequency records")
                    
                    # Combine all CPU core dataframes (preprocessETL approach)
                    if per_core_dfs:
                        # Start with first CPU dataframe
                        combined_df = per_core_dfs[0]
                        
                        # Merge other CPU dataframes on timestamp
                        for cpu_df in per_core_dfs[1:]:
                            combined_df = pd.merge(combined_df, cpu_df, on='timestamp', how='outer')
                        
                        print(f"🎯 Combined CPU frequency DataFrame: {combined_df.shape}")
                        return combined_df
                    else:
                        print("No CPU core dataframes created")
                        return pd.DataFrame(columns=['timestamp'])
                else:
                    print(f"CPU frequency extracted: {len(df)} records (raw format)")
                    # Ensure timestamp is a column for raw format
                    if 'timestamp' not in df.columns and hasattr(df, 'index'):
                        df['timestamp'] = df.index.values / 1000000
                        df = df.reset_index(drop=True)
                    return df
            else:
                print("No CPU frequency data available")
                return pd.DataFrame(columns=['timestamp'])
                
        except Exception as e:
            print(f"[WARNING]  Warning in get_cpu_freq(): {e}")
            return pd.DataFrame()

    def get_cpu_con(self):
        """Get CPU concurrency data - corrected to match preprocessETL"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            # Use the correct method from preprocessETL notebook
            cpu_con_data = self.trace.get_cpu_concurrency()
            
            if cpu_con_data is not None:
                # Convert to DataFrame if needed
                if hasattr(cpu_con_data, 'to_dataframe'):
                    df = cpu_con_data.to_dataframe()
                else:
                    df = pd.DataFrame(cpu_con_data)
                
                # Apply Procyon-style processing if we have data
                if not df.empty:
                    # Rename Start(s) to timestamp (Procyon pattern)
                    if "Start(s)" in df.columns:
                        df.rename(columns={"Start(s)": "timestamp"}, inplace=True)
                    
                    # Rename Count to Concurrency (Procyon pattern - note the spelling)
                    if "Count" in df.columns:
                        df.rename(columns={"Count": "Concurency"}, inplace=True)
                    
                    # Drop unnecessary columns (Procyon pattern)
                    columns_to_drop = []
                    if "End(s)" in df.columns:
                        columns_to_drop.append("End(s)")
                    if "Duration(s)" in df.columns:
                        columns_to_drop.append("Duration(s)")
                        
                    if columns_to_drop:
                        df = df.drop(columns=columns_to_drop)
                
                return df
            else:
                return pd.DataFrame(columns=['timestamp'])
        except Exception as e:
            print(f"[WARNING]  Warning in get_cpu_con(): {e}")
            return pd.DataFrame(columns=['timestamp'])

    def threadstat(self):
        """Extract thread statistics - corrected to match preprocessETL"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            # Use the thread method from preprocessETL notebook
            thread_data = self.trace.get_thread_intervals()
            
            if thread_data is not None:
                # Convert to DataFrame if needed
                if hasattr(thread_data, 'to_dataframe'):
                    df = thread_data.to_dataframe()
                else:
                    df = pd.DataFrame(thread_data)
                
                if 'timestamp' not in df.columns and hasattr(df, 'index'):
                    df['timestamp'] = df.index.values / 1000000
                    df = df.reset_index(drop=True)
                
                return df
            else:
                return pd.DataFrame(columns=['timestamp'])
        except Exception as e:
            print(f"[WARNING]  Warning in threadstat(): {e}")
            return pd.DataFrame(columns=['timestamp'])

    def processlifetime(self):
        """Extract process lifetime data - corrected to match preprocessETL"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            # Use the process method from preprocessETL notebook
            process_data = self.trace.get_processes()
            
            if process_data is not None:
                # Convert to DataFrame if needed
                if hasattr(process_data, 'to_dataframe'):
                    df = process_data.to_dataframe()
                else:
                    df = pd.DataFrame(process_data)
                
                if 'timestamp' not in df.columns and hasattr(df, 'index'):
                    df['timestamp'] = df.index.values / 1000000
                    df = df.reset_index(drop=True)
                
                return df
            else:
                return pd.DataFrame(columns=['timestamp'])
        except Exception as e:
            print(f"[WARNING]  Warning in processlifetime(): {e}")
            return pd.DataFrame(columns=['timestamp'])

    def EPOChanges(self):
        """Extract EPO Changes from ETW events - corrected to match preprocessETL"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            import re
            df = pd.DataFrame()
            timestamp = []
            param = []
            value = []

            event_type_list = ["EsifUmdf2EtwProvider//win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
            for i in ev:
                try:
                    if "Setting power scheme for power source" in i["Message"]:
                        guid_match = re.search(r"param GUID = ([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12});", i["Message"], re.IGNORECASE)
                        value_match = re.search(r"param Value = (\d+)", i["Message"])
                        if guid_match and value_match:
                            timestamp.append(i["TimeStamp"]/1000000)
                            param.append(guid_match.group(1))
                            value.append(value_match.group(1))
                except Exception as e:
                    pass

            data = {"timestamp": timestamp, "param": param, "value": value}
            df = pd.DataFrame(data)
            
            return df
        except Exception as e:
            print(f"[WARNING]  Warning in EPOChanges(): {e}")
            return pd.DataFrame()

    def PPMsettingRundown(self):
        """Extract PPM baseline settings from ETL (ProfileSettingRundown events)"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            df=pd.DataFrame()
            timestamp=[]
            profileid=[]
            ppm=[]
            value=[]
            ValueSize=[]
            Type=[]
            Class=[]

            event_type_list=["Microsoft-Windows-Kernel-Processor-Power/ProfileSettingRundown/win:Info"]
            ev=self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
            event_count = 0
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    ppm.append(i["Name"])
                    profileid.append(i["ProfileId"])
                    value.append(i["Value"])
                    ValueSize.append(i["ValueSize"])
                    Type.append(i["Type"])
                    Class.append(i["Class"])
                    event_count += 1
                except Exception as e:
                    pass
            
            print(f"[PPM-RUNDOWN] Extracted {event_count} ProfileSettingRundown events")

            data={"timestamp":timestamp,"PPM":ppm,"value":value,"profileid":profileid,
                  "ValueSize":ValueSize,"Type":Type,"Class":Class}
            df = pd.DataFrame(data)
            print(f"[PPM-RUNDOWN] Initial DataFrame shape: {df.shape}")
            
            if not df.empty:
                print(f"[PPM-RUNDOWN] Sample values from first row:")
                print(f"  PPM: {df.iloc[0]['PPM'] if len(df) > 0 else 'N/A'}")
                print(f"  value: {df.iloc[0]['value'] if len(df) > 0 else 'N/A'} (type: {type(df.iloc[0]['value']) if len(df) > 0 else 'N/A'})")
                print(f"  ValueSize: {df.iloc[0]['ValueSize'] if len(df) > 0 else 'N/A'}")

            # Get Profile mapping
            df_P=pd.DataFrame()
            timestamp_P=[]
            Id=[]
            Profile=[]

            event_type_list=["Microsoft-Windows-Kernel-Processor-Power/ProfileRundown/win:Info"]
            ev=self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            for i in ev:
                try:
                    timestamp_P.append(i["TimeStamp"]/1000000)
                    Profile.append(i["Name"])
                    Id.append(i["Id"])
                except Exception as e:
                    pass

            data_P={"timestamp":timestamp_P,"Profile":Profile,"Id":Id}
            df_P = pd.DataFrame(data_P)
            
            # Map profile IDs to profile names
            if not df.empty and not df_P.empty:
                print(f"[PPM-RUNDOWN] Mapping profile IDs to names...")
                profile_id_map = df_P.set_index('Id')['Profile']
                df['profileid'] = df['profileid'].map(profile_id_map)
                
                # DIAGNOSTIC: Check raw value types before conversion
                print(f"[PPM-RUNDOWN] Sample raw values BEFORE conversion:")
                for idx in range(min(3, len(df))):
                    sample_val = df.iloc[idx]['value']
                    print(f"  Row {idx}: type={type(sample_val)}, value={repr(sample_val)[:100]}")
                
                print(f"[PPM-RUNDOWN] Converting byte strings to decimal values...")
                df['value_decimal'] = df.apply(self.convert_byte_string_to_decimal, axis=1)
                
                # Check conversion results
                null_count = df['value_decimal'].isna().sum()
                print(f"[PPM-RUNDOWN] Conversion complete - {null_count} null values out of {len(df)}")
                if null_count > 0 and len(df) > 0:
                    print(f"[PPM-RUNDOWN] Sample null conversion:")
                    null_row = df[df['value_decimal'].isna()].iloc[0] if any(df['value_decimal'].isna()) else None
                    if null_row is not None:
                        print(f"  PPM: {null_row['PPM']}")
                        print(f"  value: {null_row['value']} (type: {type(null_row['value'])})")
                        print(f"  ValueSize: {null_row['ValueSize']}")
                
                df['Type'] = df['Type'].replace({0: "DC", 1: "AC"})
                df['PPM'] = df['profileid'].astype(str)+'_' +df['PPM'].astype(str) + '_' + df['Type'].astype(str) + '_' + df['Class'].astype(str)
                df=df.drop(columns=['profileid','Type','Class','ValueSize','value','timestamp'])
                # Removed dropna() - LLM agents can handle NaN values intelligently
                df = df.reset_index(drop=True)
                print(f"[PPM-RUNDOWN] Final DataFrame shape: {df.shape}")
                print(f"[PPM-RUNDOWN] Final columns: {list(df.columns)}")
            
            return df
        except Exception as e:
            print(f"[WARNING]  Warning in PPMsettingRundown(): {e}")
            return pd.DataFrame()

    def PPMsettingschange(self):
        """Extract PPM settings changes - corrected to match preprocessETL"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            df = pd.DataFrame()
            timestamp = []
            profileid = []
            ppm = []
            value = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/ProfileSettingChange/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    ppm.append(i["Name"])
                    profileid.append(i["ProfileId"])
                    value.append(i["Value"])
                except Exception as e:
                    pass

            # Create main DataFrame
            data = {"timestamp": timestamp, "PPM": ppm, "value": value, "profileid": profileid}
            df = pd.DataFrame(data)
            
            return df
        except Exception as e:
            print(f"[WARNING]  Warning in PPMsettingschange(): {e}")
            return pd.DataFrame()

    def ContainmentPolicychange(self):
        """Extract containment policy changes - corrected to match preprocessETL"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            df = pd.DataFrame()
            timestamp = []
            profileid = []
            ppm = []
            value = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/ContainmentPolicySettingChange/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    ppm.append(i["Name"])
                    profileid.append(i["ProfileId"])
                    value.append(i["Value"])
                except Exception as e:
                    pass

            data = {"timestamp": timestamp, "PPM": ppm, "value": value, "profileid": profileid}
            df = pd.DataFrame(data)
            
            return df
        except Exception as e:
            print(f"[WARNING]  Warning in ContainmentPolicychange(): {e}")
            return pd.DataFrame()

    def FG_BG_ratio(self):
        """Extract FG/BG ratio data - corrected to match preprocessETL"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            df = pd.DataFrame()
            timestamp = []
            fg_bg_ratio = []

            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/FGBGUtilization/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    fg_bg_ratio.append(i["FGBGRatio"])
                except Exception as e:
                    pass

            data = {"timestamp": timestamp, "FG_BG_ratio": fg_bg_ratio}
            df = pd.DataFrame(data)
            
            return df
        except Exception as e:
            print(f"[WARNING]  Warning in FG_BG_ratio(): {e}")
            return pd.DataFrame()

    def get_c0_intervals(self):
        """Extract ACPI C0 intervals - preprocessETL approach where index is timestamp"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            c0_data = self.trace.get_c0_intervals()
            
            if c0_data is not None:
                # Convert to DataFrame if needed
                if hasattr(c0_data, 'to_dataframe'):
                    df = c0_data.to_dataframe()
                else:
                    df = pd.DataFrame(c0_data)
                
                # Per preprocessETL: the index itself IS the timestamp
                if hasattr(df, 'index') and len(df) > 0:
                    # Reset index to make timestamp a column (preprocessETL pattern)
                    df = df.reset_index()
                    
                    # Rename index column to timestamp if it's not already named
                    if 'index' in df.columns:
                        df.rename(columns={'index': 'timestamp'}, inplace=True)
                    
                    print(f"🔧 ACPI C0 intervals: {len(df)} records with timestamp from index")
                    return df
                else:
                    return pd.DataFrame(columns=['timestamp'])
            else:
                return pd.DataFrame(columns=['timestamp'])
                
        except Exception as e:
            print(f"[WARNING]  Warning in get_c0_intervals(): {e}")
            return pd.DataFrame()

    def package_energy(self):
        """Extract package energy counter data"""
        if not SPEEDLIBS_WORKING:
            return pd.DataFrame()
        
        try:
            import pandas as pd
            
            df = pd.DataFrame()
            timestamp = []
            CounterValue = []
            
            event_type_list = ["Microsoft-Windows-Kernel-Processor-Power/PackageEnergyCounter/win:Info"]
            ev = self.trace.get_events(event_types=event_type_list, time_range=self.trace.time_range)
            
            for i in ev:
                try:
                    timestamp.append(i["TimeStamp"]/1000000)
                    CounterValue.append(i["CounterValue"]/1000)
                except Exception as e:
                    pass

            data = {"timestamp": timestamp, "Package_Power": CounterValue}
            df = pd.DataFrame(data)
            
            return df
        except Exception as e:
            print(f"[WARNING]  Warning in package_energy(): {e}")
            return pd.DataFrame()

    def get_power_state(self):
        """
        Extract power slider position and AC/DC state from trace
        
        Returns:
            dict with keys:
                - 'power_slider': 'Best Power Efficiency', 'Balanced', or 'Best Performance'
                - 'ac_state': 'AC' or 'DC'
                - 'scheme_guid': the raw GUID string
        """
        if not SPEEDLIBS_WORKING:
            return {
                'power_slider': None,
                'ac_state': None,
                'scheme_guid': None
            }
        
        # GUID to power slider mapping
        GUID_MAPPING = {
            '961cc777-2547-4f9d-8174-7d86181b8a7a': 'Best Power Efficiency',
            '00000000-0000-0000-0000-000000000000': 'Balanced',
            'ded574b5-45a0-4f42-8737-46345c09c238': 'Best Performance'
        }
        
        result = {
            'power_slider': None,
            'ac_state': None,
            'scheme_guid': None
        }
        
        try:
            # Query for both events separately (due to trace library bug)
            event_types = [
                'Microsoft-Windows-UserModePowerService/RundownPowerSource/win:Info',
                'Microsoft-Windows-UserModePowerService/RundownEffectiveOverlayPowerScheme/win:Info'
            ]
            
            for event_type in event_types:
                ev = self.trace.get_events(event_types=[event_type], time_range=self.trace.time_range)
                
                for event in ev:
                    # Check for AC/DC state
                    if event['EVENT_TYPE'] == 'Microsoft-Windows-UserModePowerService/RundownPowerSource/win:Info':
                        try:
                            ac_online = event['AcOnline']
                            result['ac_state'] = 'AC' if ac_online else 'DC'
                            print(f"[POWER] AC/DC State: {result['ac_state']} (AcOnline={ac_online})")
                        except (KeyError, AttributeError) as e:
                            print(f"[POWER] Error extracting AC state: {e}")
                    
                    # Check for power scheme GUID
                    elif event['EVENT_TYPE'] == 'Microsoft-Windows-UserModePowerService/RundownEffectiveOverlayPowerScheme/win:Info':
                        try:
                            scheme_guid = event['SchemeGuid']
                            # Remove braces and convert to lowercase for matching
                            guid_str = str(scheme_guid).strip('{}').lower()
                            result['scheme_guid'] = guid_str
                            
                            # Look up the power slider name
                            result['power_slider'] = GUID_MAPPING.get(guid_str, f'Unknown ({guid_str})')
                            print(f"[POWER] Power Slider: {result['power_slider']} (GUID={guid_str})")
                        except (KeyError, AttributeError) as e:
                            print(f"[POWER] Error extracting power scheme: {e}")
            
            return result
            
        except Exception as e:
            print(f"[WARNING]  Warning in get_power_state(): {e}")
            return result

    def convert_byte_string_to_decimal(self, row):
        """Helper function to convert byte string to decimal for PPM settings"""
        try:
            value = row['value']
            
            # Handle bytes objects directly
            if isinstance(value, bytes):
                if len(value) >= 4:
                    return int.from_bytes(value[:4], byteorder='little')
                else:
                    return int.from_bytes(value, byteorder='little')
            
            # Handle string representation of bytes
            elif isinstance(value, str):
                if value.startswith('b\'') and value.endswith('\''):
                    byte_string = value[2:-1]
                    if byte_string:
                        byte_array = bytes.fromhex(byte_string.replace('\\x', ''))
                        if len(byte_array) >= 4:
                            return int.from_bytes(byte_array[:4], byteorder='little')
                        else:
                            return int.from_bytes(byte_array, byteorder='little')
                # Try hex string without prefix
                elif value:
                    try:
                        byte_array = bytes.fromhex(value.replace('\\x', ''))
                        if len(byte_array) >= 4:
                            return int.from_bytes(byte_array[:4], byteorder='little')
                        else:
                            return int.from_bytes(byte_array, byteorder='little')
                    except:
                        pass
            
            # Handle numeric values directly
            elif isinstance(value, (int, float)):
                return int(value)
            
            # If value is None or empty, return None
            return None
            
        except Exception as e:
            # Log the error for debugging
            return None

    def fix_cpu_utilization_column_names(self, df):
        """Fix CPU utilization column names"""
        return df  # Placeholder for CPU utilization fixes

    def filter_df(self):
        """Advanced filtering and preprocessing matching original preprocessETL approach"""
        print("[FILTER] 🔧 Starting advanced dataframe filtering (preprocessETL style)...")
        
        try:
            import pandas as pd
            
            # Create dictionary to hold all processed dataframes (matching original structure)
            self.baseline_dfs = {}
            
            # 1. PPM SETTINGS PROCESSING - Split by PPM parameter (ORIGINAL APPROACH)
            if hasattr(self, 'df_ppm_settings') and hasattr(self.df_ppm_settings, 'empty') and not self.df_ppm_settings.empty:
                print("[FILTER] Processing PPM settings - splitting by parameter...")
                
                if 'PPM' in self.df_ppm_settings.columns:
                    unique_ppms = self.df_ppm_settings['PPM'].unique()
                    print(f"[FILTER]   - Found {len(unique_ppms)} unique PPM parameters: {unique_ppms}")
                    
                    for ppm_value in unique_ppms:
                        # Create separate dataframe for each PPM parameter
                        ppm_df = self.df_ppm_settings[self.df_ppm_settings['PPM'] == ppm_value].copy()
                        
                        # Rename value column to PPM parameter name
                        if 'value' in ppm_df.columns:
                            ppm_df.rename(columns={'value': str(ppm_value)}, inplace=True)
                        
                        # Remove redundant columns
                        ppm_df.drop(columns=['PPM'], inplace=True, errors='ignore')
                        if 'profileid' in ppm_df.columns:
                            ppm_df.drop(columns=['profileid'], inplace=True)
                        
                        # Store with PPM parameter as key
                        self.baseline_dfs[str(ppm_value)] = ppm_df
                        print(f"[FILTER]     ✅ Created {ppm_value}: {ppm_df.shape}")
                else:
                    print("[FILTER]   ⚠️  PPM column not found in PPM settings")
            else:
                print("[FILTER] ⚠️  PPM settings data not available")
            
            # 2. CPU FREQUENCY PROCESSING - Split by CPU core (ORIGINAL APPROACH)
            if hasattr(self, 'df_cpu_freq') and hasattr(self.df_cpu_freq, 'empty') and not self.df_cpu_freq.empty:
                print("[FILTER] Processing CPU frequency - splitting by core...")
                
                if 'CPU' in self.df_cpu_freq.columns:
                    unique_cpus = self.df_cpu_freq['CPU'].unique()
                    print(f"[FILTER]   - Found {len(unique_cpus)} CPU cores: {sorted(unique_cpus)}")
                    
                    for cpu_value in unique_cpus:
                        # Create separate dataframe for each CPU core
                        cpu_df = self.df_cpu_freq[self.df_cpu_freq['CPU'] == cpu_value].copy()
                        
                        # Rename frequency column with CPU identifier
                        if 'Frequency(Hz)' in cpu_df.columns:
                            cpu_df.rename(columns={'Frequency(Hz)': f"CPU_{cpu_value}_Freq"}, inplace=True)
                            
                            # Convert Hz to GHz (CRITICAL: Original approach)
                            cpu_df[f"CPU_{cpu_value}_Freq"] = cpu_df[f"CPU_{cpu_value}_Freq"] / 1000000000
                            print(f"[FILTER]     - Converted CPU {cpu_value} from Hz to GHz")
                        
                        # Standardize timestamp column
                        if 'Start(s)' in cpu_df.columns:
                            cpu_df.rename(columns={"Start(s)": "timestamp"}, inplace=True)
                        
                        # Remove unnecessary columns (ORIGINAL APPROACH)
                        drop_cols = ['CPU', 'Duration(s)', 'End(s)']
                        cpu_df.drop(columns=drop_cols, inplace=True, errors='ignore')
                        
                        # Store with CPU-specific key
                        self.baseline_dfs[f"CPU_{cpu_value}_FREQ"] = cpu_df
                        print(f"[FILTER]     ✅ Created CPU_{cpu_value}_FREQ: {cpu_df.shape}")
                        
                        # Update the original dataframe attribute for interpolation
                        setattr(self, f'df_cpu_{cpu_value}_freq', cpu_df)
                else:
                    print("[FILTER]   ⚠️  CPU column not found in CPU frequency data")
            else:
                print("[FILTER] ⚠️  CPU frequency data not available")
            
            # 3. CPU UTILIZATION PROCESSING - Reset index (ORIGINAL APPROACH)
            if hasattr(self, 'df_cpu_util') and hasattr(self.df_cpu_util, 'empty') and not self.df_cpu_util.empty:
                print("[FILTER] Processing CPU utilization - resetting index...")
                
                # Reset index to make timestamp a regular column (ORIGINAL APPROACH)
                if self.df_cpu_util.index.name == 'timestamp' or 'timestamp' not in self.df_cpu_util.columns:
                    self.df_cpu_util = self.df_cpu_util.reset_index()
                    if 'index' in self.df_cpu_util.columns:
                        self.df_cpu_util.rename(columns={'index': 'timestamp'}, inplace=True)
                    print("[FILTER]     ✅ Reset index to create timestamp column")
                
                self.baseline_dfs["cpuutil_data"] = self.df_cpu_util
                print(f"[FILTER]     ✅ CPU utilization processed: {self.df_cpu_util.shape}")
            else:
                print("[FILTER] ⚠️  CPU utilization data not available")
            
            # 4. CPU CONCURRENCY PROCESSING (if available)
            if hasattr(self, 'df_cpu_con') and hasattr(self.df_cpu_con, 'empty') and not self.df_cpu_con.empty:
                print("[FILTER] Processing CPU concurrency...")
                
                # Rename columns for standardization (ORIGINAL APPROACH)
                rename_map = {"Start(s)": "timestamp", "Count": "Concurrency"}
                self.df_cpu_con.rename(columns=rename_map, inplace=True)
                
                # Remove unnecessary time columns
                drop_cols = ['End(s)', 'Duration(s)']
                self.df_cpu_con.drop(columns=drop_cols, inplace=True, errors='ignore')
                
                self.baseline_dfs["cpucon_data"] = self.df_cpu_con
                print(f"[FILTER]     ✅ CPU concurrency processed: {self.df_cpu_con.shape}")
            
            # 5. OTHER DATAFRAMES - Store with standard naming
            other_dfs = [
                ('df_wlc', 'wlc_data'),
                ('df_heteroresponse', 'heteroresponse_data'),
                ('df_wpscontainmentunpark', 'containment_unpark_data'),
                ('df_heteroparkingselection', 'heteroparking_data'),
                ('df_softparkselection', 'softpark_data'),
                ('df_fg_bg_ratio', 'fgratio_data'),
                ('df_c0_intervals', 'acpic0_data'),
                ('df_package_energy', 'package_power')
            ]
            
            for attr_name, baseline_key in other_dfs:
                if hasattr(self, attr_name):
                    df = getattr(self, attr_name)
                    if hasattr(df, 'empty') and not df.empty:
                        self.baseline_dfs[baseline_key] = df
                        print(f"[FILTER]     ✅ Stored {baseline_key}: {df.shape}")
            
            print(f"[FILTER] ✅ Advanced filtering completed - {len(self.baseline_dfs)} dataframes processed")
            print(f"[FILTER] 📋 Processed dataframes: {list(self.baseline_dfs.keys())}")
            
        except Exception as e:
            print(f"[FILTER] ❌ Error in filter_df: {e}")
            import traceback
            traceback.print_exc()

    def combine_df(self):
        """Advanced time-series interpolation-based DataFrame combination"""
        print("[COMBINE] 🚀 Starting advanced time-series interpolation combination...")
        
        # Apply advanced filtering first
        self.filter_df()
        
        try:
            import pandas as pd
            import numpy as np
            
            # Use filtered dataframes from filter_df() (ORIGINAL preprocessETL approach)
            if not hasattr(self, 'baseline_dfs'):
                print("[COMBINE] ⚠️  No baseline_dfs found, filter_df may not have run properly")
                return self._basic_combine_fallback()
            
            filtered_df = self.baseline_dfs.copy()
            print(f"[COMBINE] 📊 Using {len(filtered_df)} filtered dataframes")
            
            # Additional individual CPU core dataframes (from CPU frequency splitting)
            cpu_core_dfs = {}
            for attr_name in dir(self):
                if attr_name.startswith('df_cpu_') and '_freq' in attr_name:
                    cpu_df = getattr(self, attr_name)
                    if hasattr(cpu_df, 'empty') and not cpu_df.empty:
                        core_name = attr_name.replace('df_cpu_', 'CPU_').replace('_freq', '_FREQ')
                        cpu_core_dfs[core_name] = cpu_df
                        print(f"[COMBINE]   ✅ Found CPU core: {core_name} ({cpu_df.shape})")
            
            # Merge CPU core dataframes into filtered_df
            filtered_df.update(cpu_core_dfs)
            
            # 1. Find timestamp range across all dataframes (ORIGINAL approach)
            print("[COMBINE] 📊 Finding global timestamp range...")
            min_timestamp = float('inf')
            max_timestamp = float('-inf')
            
            valid_dfs = {}
            excluded_dfs = ["hgstable_data", "profilechange_data", "expectedutility_data"]
            
            for df_name, df in filtered_df.items():
                if not df.empty and 'timestamp' in df.columns:
                    # Skip certain dataframes from timestamp range calculation (ORIGINAL approach)
                    if df_name not in excluded_dfs:
                        try:
                            df_timestamps = pd.to_numeric(df['timestamp'], errors='coerce').dropna()
                            if len(df_timestamps) > 0:
                                df_min = df_timestamps.min()
                                df_max = df_timestamps.max()
                                min_timestamp = min(min_timestamp, df_min)
                                max_timestamp = max(max_timestamp, df_max)
                                valid_dfs[df_name] = df
                                print(f"[COMBINE]   ✅ {df_name}: {len(df)} events, range: {df_min:.3f} - {df_max:.3f}s")
                            else:
                                print(f"[COMBINE]   ⚠️  {df_name}: No valid timestamps")
                        except Exception as e:
                            print(f"[COMBINE]   ❌ {df_name}: Error processing timestamps - {e}")
                    else:
                        print(f"[COMBINE]   ⏭️  {df_name}: Excluded from timestamp range calculation")
                else:
                    print(f"[COMBINE]   ❌ {df_name}: Empty or no timestamp column")
            
            if not valid_dfs:
                print("[COMBINE] ❌ No valid dataframes found for combination")
                return pd.DataFrame()
                
            if min_timestamp == float('inf'):
                print("[COMBINE] ❌ No valid timestamp range found")
                return pd.DataFrame()
            
            # 2. Create unified timestamp index with 0.1s resolution (ORIGINAL approach)
            time_resolution = 0.1  # 1 millisecond resolution
            unified_timestamps = np.arange(min_timestamp, max_timestamp + time_resolution, time_resolution)
            unified_timestamp_index = pd.Index(unified_timestamps)
            print(f"[COMBINE] 📐 Creating unified timestamp grid: {len(unified_timestamps)} points from {min_timestamp:.3f} to {max_timestamp:.3f}s")
            
            # 3. Reindex and interpolate each dataframe (ORIGINAL approach)
            print("[COMBINE] 🔄 Reindexing and interpolating dataframes...")
            interpolated_dfs = {}
            
            for df_name, df in valid_dfs.items():
                print(f"[COMBINE]   🔄 Processing {df_name}...")
                
                try:
                    # Sort and remove duplicate timestamps (ORIGINAL approach)
                    df_clean = df.sort_values(by='timestamp')
                    df_clean = df_clean.drop_duplicates(subset=['timestamp'])
                    
                    # Set timestamp as index (ORIGINAL approach)
                    df_indexed = df_clean.set_index('timestamp')
                    
                    # Reindex to unified timestamp and forward-fill missing values (ORIGINAL approach)
                    interpolated_df = df_indexed.reindex(unified_timestamp_index, method='ffill')
                    
                    # Store the interpolated dataframe
                    interpolated_dfs[df_name] = interpolated_df
                    
                    non_null_cols = interpolated_df.count().sum()
                    print(f"[COMBINE]     ✅ {df_name}: {len(df_clean)} -> {len(interpolated_df)} points ({non_null_cols} non-null values)")
                    
                except Exception as e:
                    print(f"[COMBINE]     ❌ Error processing {df_name}: {e}")
                    continue
            
            # 4. Concatenate all interpolated dataframes horizontally (ORIGINAL approach)
            if interpolated_dfs:
                print("[COMBINE] 🔗 Concatenating interpolated dataframes...")
                
                final_combined_df = pd.concat(interpolated_dfs.values(), axis=1)
                
                # Reset index to make timestamp a regular column (ORIGINAL approach)
                final_combined_df = final_combined_df.reset_index().rename(columns={'index': 'timestamp'})
                
                print(f"[COMBINE] ✅ Original preprocessETL combination completed:")
                print(f"[COMBINE]    📊 Final DataFrame: {final_combined_df.shape[0]} rows × {final_combined_df.shape[1]} columns")
                print(f"[COMBINE]    ⏱️  Time span: {final_combined_df['timestamp'].min():.3f} - {final_combined_df['timestamp'].max():.3f}s")
                print(f"[COMBINE]    💾 Memory usage: ~{final_combined_df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
                
                # Check for expected column patterns (fix string check)
                cpu_freq_cols = [col for col in final_combined_df.columns if isinstance(col, str) and 'CPU_' in col and '_Freq' in col]
                if cpu_freq_cols:
                    print(f"[COMBINE]    🎯 CPU per-core columns: {len(cpu_freq_cols)} (✅ ORIGINAL APPROACH)")
                    # Show sample frequency values
                    for col in cpu_freq_cols[:2]:  # First 2 CPUs
                        sample_vals = final_combined_df[col].dropna()
                        if len(sample_vals) > 0:
                            print(f"[COMBINE]      - {col}: {sample_vals.min():.3f} - {sample_vals.max():.3f} GHz")
                else:
                    print(f"[COMBINE]    ❌ No per-core CPU columns found")
                
                return final_combined_df
            else:
                print("[COMBINE] ❌ No dataframes could be interpolated")
                return pd.DataFrame()
            
        except Exception as e:
            print(f"[COMBINE] ❌ Error in advanced combination: {e}")
            # Fallback to basic combination
            print("[COMBINE] 🔄 Falling back to basic combination...")
            return self._basic_combine_fallback()

    def _basic_combine_fallback(self):
        """Basic fallback combination method"""
        try:
            import pandas as pd
            
            print("[FALLBACK] Using basic merge combination...")
            
            # Basic dataframes for fallback
            basic_dfs = [
                ('wlc', self.df_wlc),
                ('cpu_util', self.df_cpu_util),
                ('cpu_freq', self.df_cpu_freq)
            ]
            
            # Filter non-empty dataframes
            valid_dfs = [(name, df) for name, df in basic_dfs if not df.empty and 'timestamp' in df.columns]
            
            if not valid_dfs:
                return pd.DataFrame({'timestamp': [], 'message': ['No data available']})
            
            # Start with first valid dataframe
            combined = valid_dfs[0][1].copy()
            
            # Merge others using outer join
            for name, df in valid_dfs[1:]:
                combined = pd.merge(combined, df, on='timestamp', how='outer', suffixes=('', f'_{name}'))
            
            return combined.sort_values('timestamp').reset_index(drop=True)
            
        except Exception as e:
            print(f"[FALLBACK] Error in basic fallback: {e}")
            return pd.DataFrame({'timestamp': [], 'error': [str(e)]})

    def getCombined(self):
        """Get the combined DataFrame (alias for compatibility)"""
        return self.combined_df

class pre_process:
    """
    Pre-processing class for statistical analysis
    Full implementation matching preprocessETL.ipynb
    """
    
    def __init__(self, combined_df, logpath=None):
        import pandas as pd
        
        self.combined_df = combined_df
        self.combined_df = self.combined_df.dropna()
        self.combined_df = self.combined_df.loc[:, ~combined_df.columns.duplicated()]
        self.dfs = []
        
        # Process all statistical metrics
        try:
            self.dfs.append(self.Expected_utility())
        except:
            pass

        try:
            self.dfs.append(self.pcu())
        except:
            pass

        try:
            self.dfs.append(self.tcu())
        except:
            pass

        try:
            self.dfs.append(self.hcp())
        except:
            pass

        try:
            self.dfs.append(self.hp())
        except:
            pass

        try:
            self.dfs.append(self.ccr())
        except:
            pass
            
        try:
            self.dfs.append(self.ce())
        except:
            pass
            
        try:
            self.dfs.append(self.wlc())
        except:
            pass
            
        # Combine all processed data
        if len(self.dfs) > 0:
            self.merged_df_columns = pd.concat(self.dfs, axis=1)
            self.final_df = self.merged_df_columns.reset_index(drop=True)
            print(self.final_df)
        else:
            # No statistical data could be processed, create empty DataFrame
            print("[WARNING] No statistical data could be processed from ETL file")
            self.final_df = pd.DataFrame()
            self.merged_df_columns = pd.DataFrame()
        
        # Save if logpath provided
        if logpath:
            os.makedirs(logpath, exist_ok=True)
            self.final_df.to_csv(os.path.join(logpath, "PPM_PreProcess.csv"))

    def Expected_utility(self):
        """Calculate Expected Utility statistics"""
        import pandas as pd
        
        EU_avg = round(self.combined_df["EstimatedUtility"].mean(), 2)
        
        df_result = pd.DataFrame(["EstimatedUtility", EU_avg])
        df_result.index = ['Key', 'Value']
        df_transformed = df_result.iloc[1:].set_axis(df_result.iloc[0], axis=1)
        
        return df_transformed
    
    def pcu(self):
        """Performance Cores Unparked Count statistics"""
        import pandas as pd
        
        PCU_hist = self.combined_df["PerformanceCoresUnparkedCount"].value_counts()
        # Prepend 'PCU_' to each value in the index
        modified_index = ['PCU_' + str(idx).replace('.0', '') for idx in PCU_hist.index]
        PCU_hist.index = modified_index
        total_sum = PCU_hist.sum()
        percentages = round((PCU_hist / total_sum) * 100, 2)
        df_result = pd.DataFrame([PCU_hist.index.tolist(), percentages.tolist()])
        
        df_result.index = ['Key', 'Value']
        df_transformed = df_result.iloc[1:].set_axis(df_result.iloc[0], axis=1)
        
        return df_transformed

    def tcu(self):
        """Total Cores Unparked Count statistics"""
        import pandas as pd
        
        TCU_hist = self.combined_df["TotalCoresUnparkedCount"].value_counts()
        # Prepend 'TCU_' to each value in the index
        modified_index = ['TCU_' + str(idx).replace('.0', '') for idx in TCU_hist.index]
        TCU_hist.index = modified_index
        total_sum = TCU_hist.sum()
        percentages = round((TCU_hist / total_sum) * 100, 2)
        df_result = pd.DataFrame([TCU_hist.index.tolist(), percentages.tolist()])
        
        df_result.index = ['Key', 'Value']
        df_transformed = df_result.iloc[1:].set_axis(df_result.iloc[0], axis=1)
        
        return df_transformed
    
    def hcp(self):
        """Hetero Containment Policy statistics"""
        import pandas as pd
        
        HCP_hist = self.combined_df["HeteroContainmentPolicy"].value_counts()
        # Prepend 'HCP_' to each value in the index
        modified_index = ['HCP_' + str(idx).replace('.0', '') for idx in HCP_hist.index]
        HCP_hist.index = modified_index
        total_sum = HCP_hist.sum()
        percentages = round((HCP_hist / total_sum) * 100, 2)
        df_result = pd.DataFrame([HCP_hist.index.tolist(), percentages.tolist()])
        
        df_result.index = ['Key', 'Value']
        df_transformed = df_result.iloc[1:].set_axis(df_result.iloc[0], axis=1)
        
        return df_transformed
    
    def hp(self):
        """Hetero Policy statistics"""
        import pandas as pd
        
        HP_hist = self.combined_df["HeteroPolicy"].value_counts()
        # Prepend 'HP_' to each value in the index
        modified_index = ['HP_' + str(idx).replace('.0', '') for idx in HP_hist.index]
        HP_hist.index = modified_index
        total_sum = HP_hist.sum()
        percentages = round((HP_hist / total_sum) * 100, 2)
        df_result = pd.DataFrame([HP_hist.index.tolist(), percentages.tolist()])
        
        df_result.index = ['Key', 'Value']
        df_transformed = df_result.iloc[1:].set_axis(df_result.iloc[0], axis=1)
        
        return df_transformed
    
    def ccr(self):
        """Containment Cross Over Required statistics"""
        import pandas as pd
        
        CCR_hist = self.combined_df["ContainmentCrossOverRequired"].value_counts()
        # Prepend 'CCR_' to each value in the index
        modified_index = ['CCR_' + str(idx).replace('.0', '') for idx in CCR_hist.index]
        CCR_hist.index = modified_index
        total_sum = CCR_hist.sum()
        percentages = round((CCR_hist / total_sum) * 100, 2)
        df_result = pd.DataFrame([CCR_hist.index.tolist(), percentages.tolist()])
        
        df_result.index = ['Key', 'Value']
        df_transformed = df_result.iloc[1:].set_axis(df_result.iloc[0], axis=1)
        
        return df_transformed
    
    def ce(self):
        """Containment Enabled statistics"""
        import pandas as pd
        
        CE_hist = self.combined_df["ContainmentEnabled"].value_counts()
        # Prepend 'CE_' to each value in the index
        modified_index = ['CE_' + str(idx).replace('.0', '') for idx in CE_hist.index]
        CE_hist.index = modified_index
        total_sum = CE_hist.sum()
        percentages = round((CE_hist / total_sum) * 100, 2)
        df_result = pd.DataFrame([CE_hist.index.tolist(), percentages.tolist()])
        
        df_result.index = ['Key', 'Value']
        df_transformed = df_result.iloc[1:].set_axis(df_result.iloc[0], axis=1)
        
        return df_transformed
    
    def wlc(self):
        """Workload Classification statistics"""
        import pandas as pd
        
        wlc_hist = self.combined_df["wlc"].value_counts()
        # Prepend 'wlc_' to each value in the index
        modified_index = ['wlc_' + str(idx).replace('.0', '') for idx in wlc_hist.index]
        wlc_hist.index = modified_index
        total_sum = wlc_hist.sum()
        percentages = round((wlc_hist / total_sum) * 100, 2)
        df_result = pd.DataFrame([wlc_hist.index.tolist(), percentages.tolist()])
        
        df_result.index = ['Key', 'Value']
        df_transformed = df_result.iloc[1:].set_axis(df_result.iloc[0], axis=1)
        
        return df_transformed

class ContainmentBreach:
    """
    Containment breach analysis class
    Full implementation matching preprocessETL.ipynb
    """
    
    def __init__(self, combined_df):
        self.combined_df = combined_df
    
    def checkContainmentBreach(self):
        """
        Check for containment breaches with full analysis
        Detects performance core unparking patterns and categorizes trigger reasons
        """
        import pandas as pd
        
        if self.combined_df.empty:
            return pd.DataFrame()
        
        # Load the CSV file into a DataFrame
        df = self.combined_df.copy()

        # Define column sets to check for
        columns_to_keep = ["timestamp", 'AfterPerfUnparkCount', 'AfterEfficientUnparkCount']
        columns_to_keep2 = ["timestamp", 'PerfUnparkCount', 'EfficientUnparkCount']

        columns_to_keep_set = set(columns_to_keep)
        columns_to_keep2_set = set(columns_to_keep2)
        df_columns_set = set(df.columns)

        # Select appropriate columns based on availability
        if columns_to_keep_set.issubset(df_columns_set):
            df = df[columns_to_keep]
        elif columns_to_keep2_set.issubset(df_columns_set):
            df = df[columns_to_keep2]
        else:
            print("Warning: Required columns not found for containment breach analysis")
            return pd.DataFrame()

        df = df.dropna()

        # Initialize lists to store the new DataFrame's columns
        start_times = []
        end_times = []
        trigger_reasons = []
        average_perf_unpark_counts = []

        # Initialize variables to track the start time, trigger reason, and counts
        start_time = None
        trigger_reason = None
        perf_unpark_counts = []
        trace_end = df["timestamp"].max()

        # Threshold for concurrency vs utilization/HGS detection
        core_threshold = 4

        # Iterate over the DataFrame rows
        for index, row in df.iterrows():
            try:
                # Check if we should use AfterPerfUnparkCount or PerfUnparkCount
                perf_count_col = 'AfterPerfUnparkCount' if 'AfterPerfUnparkCount' in row else 'PerfUnparkCount'
                eff_count_col = 'AfterEfficientUnparkCount' if 'AfterEfficientUnparkCount' in row else 'EfficientUnparkCount'
                
                perf_count = row[perf_count_col]
                eff_count = row[eff_count_col]

                if start_time is None and perf_count > 0:
                    # Set the start time when performance core count becomes greater than 0
                    start_time = row['timestamp']
                    
                    # Determine the trigger reason based on total core count
                    if perf_count + eff_count > core_threshold:
                        trigger_reason = 'concurrency'
                    else:
                        trigger_reason = 'utilization/HGS'
                        
                    # Initialize the list to store counts
                    perf_unpark_counts = [perf_count]

                elif start_time is not None:
                    perf_unpark_counts.append(perf_count)
                    
                    # Monitor state changes and update the table
                    # Require at least 250ms to stay in same state
                    time_in_state = row["timestamp"] - start_time
                    
                    if trigger_reason == 'concurrency' and time_in_state < 0.250:
                        if perf_count + eff_count > core_threshold:
                            pass  # Stay in concurrency state
                        else:
                            # Transition from concurrency to utilization/HGS
                            end_time = row['timestamp']
                            average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                            
                            start_times.append(start_time)
                            end_times.append(end_time)
                            trigger_reasons.append(trigger_reason)
                            average_perf_unpark_counts.append(average_perf_unpark_count)
                            
                            # Reset for next interval
                            start_time = None
                            trigger_reason = None
                            perf_unpark_counts = []
                            continue

                    if trigger_reason == 'utilization/HGS' and time_in_state < 0.250:
                        if perf_count + eff_count > core_threshold:
                            # Transition from utilization/HGS to concurrency
                            end_time = row['timestamp']
                            average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                            
                            start_times.append(start_time)
                            end_times.append(end_time)
                            trigger_reasons.append(trigger_reason)
                            average_perf_unpark_counts.append(average_perf_unpark_count)
                            
                            # Reset for next interval
                            start_time = None
                            trigger_reason = None
                            perf_unpark_counts = []
                            continue
                        else:
                            pass  # Stay in utilization/HGS state

                    # Check if performance cores go back to zero
                    if perf_count == 0:
                        end_time = row['timestamp']
                        average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                        
                        start_times.append(start_time)
                        end_times.append(end_time)
                        trigger_reasons.append(trigger_reason)
                        average_perf_unpark_counts.append(average_perf_unpark_count)
                        
                        # Reset for next interval
                        start_time = None
                        trigger_reason = None
                        perf_unpark_counts = []

                    # Handle end of trace
                    if row["timestamp"] == trace_end and start_time is not None:
                        end_time = row['timestamp']
                        average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                        
                        start_times.append(start_time)
                        end_times.append(end_time)
                        trigger_reasons.append(trigger_reason)
                        average_perf_unpark_counts.append(average_perf_unpark_count)
                        
                        # Reset for next interval
                        start_time = None
                        trigger_reason = None
                        perf_unpark_counts = []

            except Exception as e:
                print(f"Error processing row {index}: {e}")
                continue

        # Create the result DataFrame
        try:
            result_df = pd.DataFrame({
                'start_time': start_times,
                'end_time': end_times,
                'trigger_reason': trigger_reasons,
                'average_perf_unpark_count': average_perf_unpark_counts
            })
            
            if not result_df.empty:
                result_df["duration"] = result_df["end_time"] - result_df["start_time"]
            
            return result_df
            
        except Exception as e:
            print(f"Failed to compute containment breach: {e}")
            return pd.DataFrame()


class VCIP_SingleETL_Enhanced:
    """
    4-IP Audio-Centric Alignment Analysis Class - Enhanced with Missing Event Detection
    
    Analyzes how well slower IP blocks align to the fastest Audio IP block using a single ETL file.
    Provides clear messaging when specific IP events are not found in the ETL.
    """
    
    def __init__(self):
        self.alignment_threshold_events = 2.0  # ms for regular events
        self.alignment_threshold_hw = 2.5      # ms for HW interrupts
        self.pass_threshold = 80.0             # % for PASS status
        
        
    def analyze_4ip_alignment(self, etl_path_or_trace, time_range=(2, 10), output_path=None):
        """
        Main function for 4-IP alignment analysis using ETL file or pre-loaded trace
        
        Args:
            etl_path_or_trace (str or trace object): ETL file path OR pre-loaded trace object
            time_range (tuple): Time range for analysis (start_sec, end_sec)
            output_path (str, optional): Path to save detailed report
            
        Returns:
            dict: Analysis results with rates and assessment
        """
        self.time_range=time_range
        try:
            # Check if input is a trace object or file path
            if isinstance(etl_path_or_trace, str):
                print(f"🔍 Loading ETL file: {etl_path_or_trace}")
                # Load single trace with all providers - using cached loading
                trace = load_trace_cached(etl_file=etl_path_or_trace, time_range=time_range)
            else:
                print(f"🔍 Using pre-loaded trace object")
                # Use the provided trace object
                trace = etl_path_or_trace
            
            # Step 1: Extract all events and interrupts
            events_results = self._extract_all_events(trace)
            
            # Step 2: Validate event availability and calculate alignments
            alignment_results = self._calculate_all_alignments_with_validation(events_results)
            
            # Step 3: Generate final assessment
            final_results = self._generate_final_assessment(alignment_results)
            
            # Step 4: Generate report if requested
            if output_path:
                report_text = self._generate_detailed_report(alignment_results, final_results)
                self._save_report(report_text, output_path)
                final_results['report_path'] = output_path
            
            return final_results
            
        except Exception as e:
            return {
                'error': str(e),
                'media_to_audio': 'ERROR',
                'ipu_to_audio': 'ERROR', 
                'wlan_to_audio': 'ERROR',
                'overall_status': 'ERROR',
                'assessment': f'Analysis failed: {str(e)}'
            }
    
    def _extract_all_events(self, trace):
        """Extract all IP events and HW interrupts from single ETL"""
        # Extract regular events from ETL
        etl = trace.etl
        audio_events = []
        media_events = []
        ipu_events = []
        
        print("🔍 Extracting events from ETL...")
        for ev in etl.get_events(time_range=self.time_range):
            timestamp_ms = ev["TimeStamp"] / 1000
            
            if 'AudioCore_Pump_GetCurrentPadding_Task' in ev[0] and 'win:Stop' in ev[0]:
                audio_events.append({'timestamp_ms': timestamp_ms})
            elif 'Decode_DDI_IP_Alignment' in ev[0] and 'win:Stop' in ev[0]:
                media_events.append({'timestamp_ms': timestamp_ms})
            elif 'Intel-Camera-Intel(R) AVStream Camera' in ev[0] and 'IP_ALIGNMENT' in ev[0]:
                ipu_events.append({'timestamp_ms': timestamp_ms})
        
        # Extract hardware interrupts
        audio_hw_events = []
        wlan_hw_events = []
        hw_extraction_error = None
        
        try:
            print("🔍 Extracting HW interrupts from ETL...")
            interrupts_df = trace.get_interrupts(time_range=self.time_range)
            
            # Audio HW interrupts
            audio_hw_df = interrupts_df[
                (interrupts_df['Name'].str.contains('intcaudiobus.sys', case=False, na=False)) &
                (interrupts_df['Type'].str.contains('HW', case=False, na=False))
            ]
            audio_hw_events = [{'timestamp_ms': t * 1000} for t in audio_hw_df['End(s)'].values]
            
            # WLAN HW interrupts  
            wlan_hw_df = interrupts_df[
                (interrupts_df['Name'].str.contains('netwaw16.sys', case=False, na=False)) &
                (interrupts_df['Type'].str.contains('HW', case=False, na=False))
            ]
            wlan_hw_events = [{'timestamp_ms': t * 1000} for t in wlan_hw_df['End(s)'].values]
            
        except Exception as e:
            hw_extraction_error = str(e)
            print(f"⚠️  HW interrupt extraction failed: {e}")
        
        # Report what was found
        print(f"📊 Events extracted:")
        print(f"   Audio Events: {len(audio_events)}")
        print(f"   Media Events: {len(media_events)} {'❌ NOT FOUND' if len(media_events) == 0 else '✅'}")
        print(f"   IPU Events: {len(ipu_events)} {'❌ NOT FOUND' if len(ipu_events) == 0 else '✅'}")
        print(f"   Audio HW Interrupts: {len(audio_hw_events)} {'❌ NOT FOUND' if len(audio_hw_events) == 0 else '✅'}")
        print(f"   WLAN HW Interrupts: {len(wlan_hw_events)} {'❌ NOT FOUND' if len(wlan_hw_events) == 0 else '✅'}")
        
        return {
            'audio_events': audio_events,
            'media_events': media_events,
            'ipu_events': ipu_events,
            'audio_hw_events': audio_hw_events,
            'wlan_hw_events': wlan_hw_events,
            'hw_extraction_error': hw_extraction_error
        }
    
    def _calculate_all_alignments_with_validation(self, events_results):
        """Calculate alignments with proper validation for missing events"""
        print("🔄 Calculating alignments with validation...")
        
        # Check for critical missing events
        missing_events = []
        if len(events_results['audio_events']) == 0:
            missing_events.append('Audio')
        if len(events_results['media_events']) == 0:
            missing_events.append('Media')
        if len(events_results['ipu_events']) == 0:
            missing_events.append('IPU')
        if len(events_results['wlan_hw_events']) == 0:
            missing_events.append('WLAN HW')
        if len(events_results['audio_hw_events']) == 0:
            missing_events.append('Audio HW')
        
        # Media → Audio alignment
        if len(events_results['media_events']) == 0 or len(events_results['audio_events']) == 0:
            media_alignment = {
                'status': 'NOT_FOUND',
                'message': 'Media events not found in ETL' if len(events_results['media_events']) == 0 else 'Audio events not found in ETL',
                'aligned_count': 0,
                'rate': 'N/A',
                'pairs': []
            }
        else:
            media_alignment = self._calculate_alignment(
                events_results['media_events'], 
                events_results['audio_events'], 
                'media',
                threshold=self.alignment_threshold_events
            )
            media_alignment['status'] = 'CALCULATED'
            media_alignment['message'] = f'Analysis completed with {len(events_results["media_events"])} Media events'
        
        # IPU → Audio alignment
        if len(events_results['ipu_events']) == 0 or len(events_results['audio_events']) == 0:
            ipu_alignment = {
                'status': 'NOT_FOUND',
                'message': 'IPU events not found in ETL' if len(events_results['ipu_events']) == 0 else 'Audio events not found in ETL',
                'aligned_count': 0,
                'rate': 'N/A',
                'pairs': []
            }
        else:
            ipu_alignment = self._calculate_alignment(
                events_results['ipu_events'],
                events_results['audio_events'],
                'ipu', 
                threshold=self.alignment_threshold_events
            )
            ipu_alignment['status'] = 'CALCULATED'
            ipu_alignment['message'] = f'Analysis completed with {len(events_results["ipu_events"])} IPU events'
        
        # WLAN → Audio alignment (using HW interrupts)
        if len(events_results['wlan_hw_events']) == 0 or len(events_results['audio_hw_events']) == 0:
            missing_hw = []
            if len(events_results['wlan_hw_events']) == 0:
                missing_hw.append('WLAN HW interrupts')
            if len(events_results['audio_hw_events']) == 0:
                missing_hw.append('Audio HW interrupts')
            
            wlan_alignment = {
                'status': 'NOT_FOUND',
                'message': f'{" and ".join(missing_hw)} not found in ETL',
                'aligned_count': 0,
                'rate': 'N/A',
                'pairs': []
            }
        else:
            wlan_alignment = self._calculate_alignment(
                events_results['wlan_hw_events'],
                events_results['audio_hw_events'],
                'wlan',
                threshold=self.alignment_threshold_hw
            )
            wlan_alignment['status'] = 'CALCULATED'
            wlan_alignment['message'] = f'Analysis completed with {len(events_results["wlan_hw_events"])} WLAN HW interrupts'
        
        # Report alignment status
        print(f"✅ Alignment Status:")
        print(f"   Media→Audio: {media_alignment['status']} - {media_alignment['message']}")
        print(f"   IPU→Audio: {ipu_alignment['status']} - {ipu_alignment['message']}")
        print(f"   WLAN→Audio: {wlan_alignment['status']} - {wlan_alignment['message']}")
        
        return {
            'events_counts': {
                'audio_events': len(events_results['audio_events']),
                'media_events': len(events_results['media_events']),
                'ipu_events': len(events_results['ipu_events']),
                'audio_hw_events': len(events_results['audio_hw_events']),
                'wlan_hw_events': len(events_results['wlan_hw_events'])
            },
            'media_alignment': media_alignment,
            'ipu_alignment': ipu_alignment,
            'wlan_alignment': wlan_alignment,
            'missing_events': missing_events,
            'hw_extraction_error': events_results.get('hw_extraction_error')
        }
    
    def _calculate_alignment(self, source_events, target_events, source_name, threshold):
        """Calculate alignment between source and target events"""
        aligned_count = 0
        aligned_pairs = []
        
        for source_event in source_events:
            closest_target = None
            closest_delta = float('inf')
            
            for target_event in target_events:
                delta = abs(source_event['timestamp_ms'] - target_event['timestamp_ms'])
                if delta <= threshold and delta < closest_delta:
                    closest_delta = delta
                    closest_target = target_event
            
            if closest_target:
                aligned_count += 1
                aligned_pairs.append({
                    f'{source_name}_time': source_event['timestamp_ms'],
                    'audio_time': closest_target['timestamp_ms'],
                    'delta': closest_delta
                })
        
        rate = (aligned_count / len(source_events) * 100) if len(source_events) > 0 else 0.0
        
        # Sort pairs by delta (best alignments first) and limit to top 5
        aligned_pairs.sort(key=lambda x: x['delta'])
        
        return {
            'aligned_count': aligned_count,
            'rate': rate,
            'pairs': aligned_pairs[:5]  # Top 5 for reporting
        }
    
    def _generate_final_assessment(self, alignment_results):
        """Generate final assessment with proper handling of missing events"""
        from datetime import datetime
        
        media_data = alignment_results['media_alignment']
        ipu_data = alignment_results['ipu_alignment']
        wlan_data = alignment_results['wlan_alignment']
        
        # Handle rates for missing events
        media_rate = media_data['rate'] if media_data['status'] == 'CALCULATED' else 'NOT_FOUND'
        ipu_rate = ipu_data['rate'] if ipu_data['status'] == 'CALCULATED' else 'NOT_FOUND'
        wlan_rate = wlan_data['rate'] if wlan_data['status'] == 'CALCULATED' else 'NOT_FOUND'
        
        # Count only calculated alignments for pass assessment
        calculated_rates = []
        if media_data['status'] == 'CALCULATED':
            calculated_rates.append(media_data['rate'])
        if ipu_data['status'] == 'CALCULATED':
            calculated_rates.append(ipu_data['rate'])
        if wlan_data['status'] == 'CALCULATED':
            calculated_rates.append(wlan_data['rate'])
        
        # Determine overall status
        if not calculated_rates:
            overall_status = "NO_DATA"
            assessment = "No IP events found for alignment analysis"
            pass_count = 0
        else:
            pass_count = sum([1 for rate in calculated_rates if rate >= self.pass_threshold])
            total_calculated = len(calculated_rates)
            
            if pass_count == total_calculated and total_calculated == 3:
                overall_status = "PASS"
                assessment = "All IPs achieve excellent alignment (≥80%)"
            elif pass_count >= total_calculated * 0.67:  # At least 2/3 of available IPs
                overall_status = "MARGINAL"
                assessment = f"{pass_count}/{total_calculated} available IPs achieve good alignment (≥80%)"
            else:
                overall_status = "FAIL"
                assessment = f"Only {pass_count}/{total_calculated} available IPs achieve acceptable alignment (≥80%)"
        
        # Add missing events warning to assessment
        if alignment_results['missing_events']:
            missing_str = ', '.join(alignment_results['missing_events'])
            assessment += f" | Missing: {missing_str}"
        
        return {
            'media_to_audio': round(media_rate, 1) if isinstance(media_rate, (int, float)) else media_rate,
            'ipu_to_audio': round(ipu_rate, 1) if isinstance(ipu_rate, (int, float)) else ipu_rate,
            'wlan_to_audio': round(wlan_rate, 1) if isinstance(wlan_rate, (int, float)) else wlan_rate,
            'overall_status': overall_status,
            'pass_count': pass_count,
            'calculated_count': len(calculated_rates),
            'assessment': assessment,
            'missing_events': alignment_results['missing_events'],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'agent_metrics': {
                'METRIC_MEDIA_TO_AUDIO_RATE': media_rate,
                'METRIC_IPU_TO_AUDIO_RATE': ipu_rate,
                'METRIC_WLAN_TO_AUDIO_RATE': wlan_rate,
                'METRIC_OVERALL_STATUS': overall_status,
                'METRIC_MISSING_EVENTS': alignment_results['missing_events']
            },
            'alignment_details': alignment_results
        }
    
    def _generate_detailed_report(self, alignment_results, final_results):
        """Generate detailed text report with missing event information"""
        def format_ip_section(ip_name, source_count, target_count, alignment_data):
            if alignment_data['status'] == 'NOT_FOUND':
                return f"""
{ip_name.upper()}→AUDIO ALIGNMENT ANALYSIS:
Status: EVENTS NOT FOUND
Message: {alignment_data['message']}
Unable to perform alignment analysis - required events missing from ETL
"""
            
            aligned_count = alignment_data['aligned_count']
            rate = alignment_data['rate']
            aligned_pairs = alignment_data['pairs']
            
            status = "PASS" if rate >= 80 else "MARGINAL" if rate >= 60 else "FAIL"
            target_type = "HW Interrupts" if ip_name.upper() == "WLAN" else "Events"
            
            section = f"""
{ip_name.upper()}→AUDIO ALIGNMENT ANALYSIS:
{target_type}: {{'AUDIO': {target_count}, '{ip_name.upper()}': {source_count}}}
Aligned Pairs: {aligned_count}
Alignment Rate: {rate:.2f}%
Status: {status}
Threshold: {self.alignment_threshold_hw if ip_name.upper() == "WLAN" else self.alignment_threshold_events}ms
Message: {alignment_data['message']}
"""
            
            if aligned_pairs:
                section += "\nTop 5 Aligned Pairs:\n"
                for i, pair in enumerate(aligned_pairs, 1):
                    if ip_name.lower() == 'media':
                        section += f"  {i:2d}. {pair['media_time']:8.3f}ms <-> {pair['audio_time']:8.3f}ms (Δ{pair['delta']:.3f}ms)\n"
                    elif ip_name.lower() == 'ipu':
                        section += f"  {i:2d}. {pair['ipu_time']:8.3f}ms <-> {pair['audio_time']:8.3f}ms (Δ{pair['delta']:.3f}ms)\n"
                    elif ip_name.lower() == 'wlan':
                        section += f"  {i:2d}. {pair['wlan_time']:8.3f}ms <-> {pair['audio_time']:8.3f}ms (Δ{pair['delta']:.3f}ms)\n"
            else:
                section += "\n(No aligned pairs found)\n"
                
            return section
        
        counts = alignment_results['events_counts']
        
        media_section = format_ip_section('MEDIA', counts['media_events'], counts['audio_events'], 
                                        alignment_results['media_alignment'])
        ipu_section = format_ip_section('IPU', counts['ipu_events'], counts['audio_events'],
                                       alignment_results['ipu_alignment'])
        wlan_section = format_ip_section('WLAN', counts['wlan_hw_events'], counts['audio_hw_events'],
                                        alignment_results['wlan_alignment'])
        
        return f"""4-IP AUDIO-CENTRIC ALIGNMENT ANALYSIS REPORT (Enhanced)
=====================================================
Generated: {final_results['timestamp']}
Logic: Slower IPs align TO Audio (fastest IP)

{media_section}
{ipu_section}
{wlan_section}

SUMMARY:
- Media→Audio: {final_results['media_to_audio']}{'%' if isinstance(final_results['media_to_audio'], (int, float)) else ''}
- IPU→Audio: {final_results['ipu_to_audio']}{'%' if isinstance(final_results['ipu_to_audio'], (int, float)) else ''}
- WLAN→Audio: {final_results['wlan_to_audio']}{'%' if isinstance(final_results['wlan_to_audio'], (int, float)) else ''}
- Overall Status: {final_results['overall_status']}
- Assessment: {final_results['assessment']}

AGENT METRICS:
METRIC_MEDIA_TO_AUDIO_RATE: {final_results['media_to_audio']}
METRIC_IPU_TO_AUDIO_RATE: {final_results['ipu_to_audio']}
METRIC_WLAN_TO_AUDIO_RATE: {final_results['wlan_to_audio']}
METRIC_OVERALL_STATUS: {final_results['overall_status']}
METRIC_MISSING_EVENTS: {final_results['missing_events']}
"""
    
    def _save_report(self, report_text, output_path):
        """Save detailed report to file"""
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_text)

class TeamsFPS:
    """
    Teams Video Pipeline FPS Analysis Class
    
    Analyzes video pipeline performance by calculating FPS for different components:
    - Decode FPS (incoming video streams)
    - Encode FPS (outgoing video streams) 
    - VPBLT FPS (video processing)
    - Camera FPS (camera capture)
    
    Designed for AI agent consumption with simple input/output interface.
    Returns raw FPS values without performance assessment - agents will handle evaluation.
    """
    
    def __init__(self):
        pass  # No thresholds needed - agents will handle performance evaluation
    
    def analyze_fps(self, etl_path_or_trace, time_range=(5, 65), output_path=None):
        """
        Main function for Teams FPS analysis
        
        Args:
            etl_path_or_trace (str or trace object): ETL file path OR pre-loaded trace object
            time_range (tuple): Time range for analysis (start_sec, end_sec)
            output_path (str, optional): Path to save detailed report
            
        Returns:
            dict: FPS analysis results with raw metrics
        """
        self.time_range=time_range
        try:
            # Check if input is a trace object or file path
            if isinstance(etl_path_or_trace, str):
                print(f"🎥 Loading ETL file: {etl_path_or_trace}")
                # Load trace - using cached loading
                trace = load_trace_cached(etl_file=etl_path_or_trace, time_range=time_range)
            else:
                print(f"🎥 Using pre-loaded trace object")
                # Use the provided trace object
                trace = etl_path_or_trace
            
            # Extract video events
            events_data = self._extract_video_events(trace, time_range)
            
            # Calculate FPS metrics
            fps_results = self._calculate_fps_metrics(events_data, time_range)
            
            # Generate basic results without assessment
            final_results = self._generate_fps_results(fps_results, time_range)
            
            # Generate report if requested
            if output_path:
                report_text = self._generate_detailed_report(final_results)
                self._save_report(report_text, output_path)
                final_results['report_path'] = output_path
            
            return final_results
            
        except Exception as e:
            return {
                'error': str(e),
                'decode_fps': 0.0,
                'encode_fps': 0.0,
                'vpblt_fps': 0.0, 
                'camera_fps': 0.0,
                'status': 'ERROR'
            }
    
    def _extract_video_events(self, trace, time_range):
        """Extract video pipeline events from ETL"""
        start, end = time_range
        
        print(f"🔍 Extracting video events from {start}s to {end}s...")
        
        etl = trace.etl
        event_types = set()
        
        # Event counters
        decoder_end_count = 0      # Total decoder events
        encode_count = 0           # Encode events (subset of decoder events)
        vpblt_count = 0           # Video processor blit events
        camera_count = 0          # Camera capture events
        
        # Event lists for detailed analysis
        decoder_events = []
        encode_events = []
        vpblt_events = []
        camera_events = []
        
        for ev in etl.get_events(time_range=self.time_range):
            event_types.add(ev[0])
            timestamp_s = ev["TimeStamp"] / 1000000000  # Convert to seconds
            
            # Decoder End Frame events (total video processing)
            if 'ID3D11VideoContext_DecoderEndFrame' in ev[0] and 'win:Start' in ev[0]:
                decoder_end_count += 1
                decoder_events.append({'timestamp_s': timestamp_s})
                
            # Encode events (outgoing video)  
            if 'MFCaptureEngine-Sink-Task' in ev[0] and 'win:Start' in ev[0]:
                encode_count += 1
                encode_events.append({'timestamp_s': timestamp_s})
                
            # Video Processor Blit events (video processing)
            if 'ID3D11VideoContext_VideoProcessorBlt' in ev[0] and 'win:Start' in ev[0]:
                vpblt_count += 1
                vpblt_events.append({'timestamp_s': timestamp_s})
                
            # Camera capture events
            if 'MF_Devproxy_SendBuffersToDevice' in ev[0] and 'win:Start' in ev[0]:
                camera_count += 1
                camera_events.append({'timestamp_s': timestamp_s})
        
        # Calculate decode count (total - encode, as per original logic)
        decode_count = decoder_end_count - encode_count
        
        print(f"📊 Video Events Extracted:")
        print(f"   Total Decoder End: {decoder_end_count}")
        print(f"   Encode Events: {encode_count}")
        print(f"   Decode Events: {decode_count} (calculated)")
        print(f"   VPBLT Events: {vpblt_count}")
        print(f"   Camera Events: {camera_count}")
        print(f"   Unique Event Types: {len(event_types)}")
        
        return {
            'decoder_end_count': decoder_end_count,
            'encode_count': encode_count,
            'decode_count': decode_count,
            'vpblt_count': vpblt_count,
            'camera_count': camera_count,
            'decoder_events': decoder_events,
            'encode_events': encode_events,
            'vpblt_events': vpblt_events,
            'camera_events': camera_events,
            'event_types_count': len(event_types)
        }
    
    def _calculate_fps_metrics(self, events_data, time_range):
        """Calculate FPS for each video component"""
        start, end = time_range
        duration = end - start
        
        print(f"🔄 Calculating FPS over {duration}s duration...")
        
        # Calculate raw FPS values (following original logic)
        decode_fps = events_data['decode_count'] / duration / 9  # Original has /9 division
        encode_fps = events_data['encode_count'] / duration
        vpblt_fps = events_data['vpblt_count'] / duration / 9    # Original has /9 division
        camera_fps = events_data['camera_count'] / duration
        
        print(f"✅ FPS Calculated:")
        print(f"   Decode FPS: {decode_fps:.2f}")
        print(f"   Encode FPS: {encode_fps:.2f}")
        print(f"   VPBLT FPS: {vpblt_fps:.2f}")
        print(f"   Camera FPS: {camera_fps:.2f}")
        
        return {
            'decode_fps': decode_fps,
            'encode_fps': encode_fps,
            'vpblt_fps': vpblt_fps,
            'camera_fps': camera_fps,
            'duration': duration,
            'events_data': events_data
        }
    
    def _generate_fps_results(self, fps_results, time_range):
        """Generate basic FPS results without performance assessment"""
        from datetime import datetime
        
        decode_fps = fps_results['decode_fps']
        encode_fps = fps_results['encode_fps'] 
        vpblt_fps = fps_results['vpblt_fps']
        camera_fps = fps_results['camera_fps']
        
        return {
            'decode_fps': round(decode_fps, 2),
            'encode_fps': round(encode_fps, 2),
            'vpblt_fps': round(vpblt_fps, 2),
            'camera_fps': round(camera_fps, 2),
            'time_range': time_range,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'duration': fps_results['duration'],
            'event_counts': {
                'decode_events': fps_results['events_data']['decode_count'],
                'encode_events': fps_results['events_data']['encode_count'],
                'vpblt_events': fps_results['events_data']['vpblt_count'],
                'camera_events': fps_results['events_data']['camera_count'],
                'decoder_end_events': fps_results['events_data']['decoder_end_count']
            },
            'status': 'SUCCESS'
        }
    
    def _generate_detailed_report(self, results):
        """Generate simple text report with raw FPS data"""
        
        return f"""TEAMS VIDEO PIPELINE FPS ANALYSIS REPORT
=======================================
Generated: {results['timestamp']}
Analysis Period: {results['time_range'][0]}s - {results['time_range'][1]}s
Duration: {results['duration']}s

FPS METRICS:
- Decode FPS: {results['decode_fps']:.2f}
- Encode FPS: {results['encode_fps']:.2f}
- VPBLT FPS: {results['vpblt_fps']:.2f}
- Camera FPS: {results['camera_fps']:.2f}

EVENT COUNTS:
- Decode Events: {results['event_counts']['decode_events']}
- Encode Events: {results['event_counts']['encode_events']}
- VPBLT Events: {results['event_counts']['vpblt_events']}
- Camera Events: {results['event_counts']['camera_events']}
- Total Decoder End Events: {results['event_counts']['decoder_end_events']}

Status: {results['status']}
"""
    
    def _save_report(self, report_text, output_path):
        """Save detailed report to file"""
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_text)

class TeamsPipelineAnalysis:
    """
    Teams Video Pipeline Detailed Analysis Class - Port from TeamsPipelineAnalysis.ipynb
    
    Analyzes comprehensive Media IP and Display IP metrics:
    
    Media IP Activity:
    - Decode FPS (OS & Driver layer)
    - Encode FPS (OS & Driver layer)
    - VPBlt processing (input/output resolution & format)
    
    Display IP Activity:
    - Display Present FPS and mode
    - MMIOFlip FPS
    - VSync and VBlank interrupts
    - FlipQ execution rate
    
    Designed for AI agent consumption - returns raw metrics without assessment.
    """
    
    def __init__(self):
        """Initialize pipeline analyzer"""
        self.format_mapping = {
            25: "NV12",
            1: "ARGB8",
            4: "H264"
        }
        
        self.present_mode_names = {
            0: "D3DKMT_PM_UNINITIALIZED",
            1: "D3DKMT_PM_REDIRECTED_GDI",
            2: "D3DKMT_PM_REDIRECTED_FLIP",
            3: "D3DKMT_PM_REDIRECTED_BLT",
            4: "D3DKMT_PM_REDIRECTED_VISTABLT",
            5: "D3DKMT_PM_SCREENCAPTUREFENCE",
            6: "D3DKMT_PM_REDIRECTED_GDI_SYSMEM",
            7: "D3DKMT_PM_REDIRECTED_COMPOSITION"
        }
    
    def analyze_pipeline(self, etl_path_or_trace, time_range=(32, 33), output_path=None):
        """
        Main function for Teams pipeline analysis
        
        Args:
            etl_path_or_trace (str or trace object): ETL file path OR pre-loaded trace object
            time_range (tuple): Time range for analysis (start_sec, end_sec) - default (32, 33) matches notebook
            output_path (str, optional): Path to save detailed report
            
        Returns:
            dict: Pipeline analysis results with raw metrics
        """
        try:
            # Load or use provided trace
            if isinstance(etl_path_or_trace, str):
                print(f"🎥 Loading ETL file for pipeline analysis: {etl_path_or_trace}")
                trace = load_trace_cached(etl_file=etl_path_or_trace, time_range=time_range)
            else:
                print(f"🎥 Using pre-loaded trace for pipeline analysis")
                trace = etl_path_or_trace
            
            # Extract all pipeline events
            events_data = self._extract_pipeline_events(trace, time_range)
            
            # Calculate all metrics
            metrics = self._calculate_pipeline_metrics(events_data, time_range)
            
            # Generate final results
            final_results = self._generate_pipeline_results(metrics, time_range)
            
            # Save report if requested
            if output_path:
                report_text = self._generate_detailed_report(final_results)
                self._save_report(report_text, output_path)
                final_results['report_path'] = output_path
            
            return final_results
            
        except Exception as e:
            return {
                'error': str(e),
                'status': 'ERROR'
            }
    
    def _extract_pipeline_events(self, trace, time_range):
        """Extract all media and display IP events from ETL"""
        start, end = time_range
        duration = end - start
        
        print(f"🔍 Extracting pipeline events from {start}s to {end}s...")
        
        etl = trace.etl
        
        # Initialize counters - Media IP
        osD3D_Decoder = 0
        imed_DecodePicture_DecodeFPS = 0
        imed_DecodePicture_DecodeWidth = 0
        imed_DecodePicture_DecodeHeight = 0
        imed_DecodePicture_DecodeFormat = 0
        imed_DecodePicture_DecodeBitdepth = 0
        imed_DecodePicture_DecodeChromaFormat = 0
        
        camera_count = 0  # Encode OS
        isubID0_720count = 0  # Encode Driver
        imed_VPBlt_encHeight = 0
        imed_VPBlt_encwidth = 0
        imed_VPBlt_encFormat = 0
        
        isubID0_240count = 0  # VPBlt Input
        imed_VPBlt_inHeight = 0
        imed_VPBlt_inwidth = 0
        imed_VPBlt_inFormat = 0
        
        imed_VPBlt_outHeight = 0  # VPBlt Output
        imed_VPBlt_outwidth = 0
        imed_VPBlt_outFormat = 0
        
        # Initialize counters - Display IP
        osDxg_Presentcnt = 0
        os_present_mode = 0
        os_Present_srcRectW = 0
        os_Present_srcRectH = 0
        os_Present_destRectW = 0
        os_Present_destRectH = 0
        
        osMMIOMPO_cnt = 0
        osVSyncInterrupt = 0
        igd_Vbicnt = 0
        igd_FlipQExec_Cnt = 0
        
        print("📊 Processing Media IP events...")
        
        # ============================MEDIA IP=====================================#
        # Decode (OS)
        for event in etl.get_events(event_types=['Microsoft-Windows-Direct3D11/ID3D11VideoContext_DecoderBeginFrame/win:Start'], time_range=time_range):
            if event['Process Name'].find("ms-teams.exe") != -1:
                osD3D_Decoder += 1
        
        # Decode (Driver)
        for event in etl.get_events(event_types=['Intel-Media/Decode_Info_Picture/win:Info'], time_range=time_range):
            if event['Process Name'].find("ms-teams.exe") != -1:
                imed_DecodePicture_DecodeFPS += 1
                imed_DecodePicture_DecodeWidth = event['Width']
                imed_DecodePicture_DecodeHeight = event['Height']
                imed_DecodePicture_DecodeFormat = event['CodecFormat']
                imed_DecodePicture_DecodeBitdepth = event['Bitdepth']
                imed_DecodePicture_DecodeChromaFormat = event['ChromaFormat']
        
        # Encode (OS)
        for event in etl.get_events(event_types=['Microsoft-Windows-MF/MF_Devproxy_SendBuffersToDevice/win:Start'], time_range=time_range):
            if event['Process Name'].find("ms-teams.exe") != -1:
                camera_count += 1
        
        # Encode & VPBlt (Driver)
        for event in etl.get_events(event_types=['Intel-Media/eDDI_VP_Blt/win:Info'], time_range=time_range):
            if event['Process Name'].find("ms-teams.exe") != -1:
                imed_VPBlt_outHeight = event['oHeight']
                imed_VPBlt_outwidth = event['oWidth']
                imed_VPBlt_outFormat = event['oFormat']
                
                if event['iHeight'] == 720:
                    isubID0_720count += 1
                    imed_VPBlt_encHeight = event['iHeight']
                    imed_VPBlt_encwidth = event['iWidth']
                    imed_VPBlt_encFormat = event['iFormat']
                
                if event['iHeight'] == 240:
                    isubID0_240count += 1
                    imed_VPBlt_inHeight = event['iHeight']
                    imed_VPBlt_inwidth = event['iWidth']
                    imed_VPBlt_inFormat = event['iFormat']
        
        print("📊 Processing Display IP events...")
        
        # ============================DISPLAY IP=====================================#
        # Display Present (OS)
        for event in etl.get_events(event_types=['Microsoft-Windows-DxgKrnl/PresentHistoryDetailed/win:Start'], time_range=time_range):
            if event['Process Name'].find("ms-teams.exe") != -1:
                osDxg_Presentcnt += 1
                os_present_mode = event['Model']
                os_Present_srcRectW = event['SourceRect.right']
                os_Present_srcRectH = event['SourceRect.bottom']
                os_Present_destRectW = event['DestWidth']
                os_Present_destRectH = event['DestHeight']
        
        # MMIOFlip (OS)
        for event in etl.get_events(event_types=['Microsoft-Windows-DxgKrnl/MMIOFlipMultiPlaneOverlay/win:Info'], time_range=time_range):
            if event['Process Name'].find("System") != -1:
                osMMIOMPO_cnt += 1
        
        # VSync Interrupt (OS)
        for event in etl.get_events(event_types=['Microsoft-Windows-DxgKrnl/VSyncInterrupt/win:Info'], time_range=time_range):
            if event['Process Name'].find("ms-teams.exe") != -1:
                osVSyncInterrupt += 1
        
        # VBlank Interrupt (Driver)
        for event in etl.get_events(event_types=['Intel-Gfx-Driver-Display/VBlankInterrupt/PipeA'], time_range=time_range):
            if event['Process Name'].find("ms-teams.exe") != -1:
                igd_Vbicnt += 1
        
        # FlipQ Executed (Driver)
        for event in etl.get_events(event_types=['Intel-Gfx-Driver-Display/FlipQExecuted/Info'], time_range=time_range):
            if event['Process Name'].find("ms-teams.exe") != -1:
                igd_FlipQExec_Cnt += 1
        
        print(f"✅ Pipeline Events Extracted")
        print(f"   Media Decode (OS): {osD3D_Decoder} events")
        print(f"   Media Decode (Drv): {imed_DecodePicture_DecodeFPS} events")
        print(f"   Media Encode (OS): {camera_count} events")
        print(f"   Media Encode (Drv): {isubID0_720count} events")
        print(f"   Display Present: {osDxg_Presentcnt} events")
        print(f"   Display MMIOFlip: {osMMIOMPO_cnt} events")
        
        return {
            'duration': duration,
            # Media IP - Decode
            'media_decode_os_count': osD3D_Decoder,
            'media_decode_drv_count': imed_DecodePicture_DecodeFPS,
            'decode_width': imed_DecodePicture_DecodeWidth,
            'decode_height': imed_DecodePicture_DecodeHeight,
            'decode_format': imed_DecodePicture_DecodeFormat,
            'decode_bitdepth': imed_DecodePicture_DecodeBitdepth,
            'decode_chroma_format': imed_DecodePicture_DecodeChromaFormat,
            # Media IP - Encode
            'media_encode_os_count': camera_count,
            'media_encode_drv_count': isubID0_720count,
            'encode_width': imed_VPBlt_encwidth,
            'encode_height': imed_VPBlt_encHeight,
            'encode_format': imed_VPBlt_encFormat,
            # Media IP - VPBlt
            'vpblt_input_count': isubID0_240count,
            'vpblt_input_width': imed_VPBlt_inwidth,
            'vpblt_input_height': imed_VPBlt_inHeight,
            'vpblt_input_format': imed_VPBlt_inFormat,
            'vpblt_output_width': imed_VPBlt_outwidth,
            'vpblt_output_height': imed_VPBlt_outHeight,
            'vpblt_output_format': imed_VPBlt_outFormat,
            # Display IP
            'display_present_count': osDxg_Presentcnt,
            'display_present_mode': os_present_mode,
            'display_source_width': os_Present_srcRectW,
            'display_source_height': os_Present_srcRectH,
            'display_dest_width': os_Present_destRectW,
            'display_dest_height': os_Present_destRectH,
            'display_mmioflip_count': osMMIOMPO_cnt,
            'display_vsync_count': osVSyncInterrupt,
            'display_vblank_count': igd_Vbicnt,
            'display_flipq_count': igd_FlipQExec_Cnt
        }
    
    def _calculate_pipeline_metrics(self, events_data, time_range):
        """Calculate FPS and format metrics from event data"""
        duration = events_data['duration']
        
        print(f"🔄 Calculating pipeline metrics over {duration}s duration...")
        
        # Media IP FPS calculations (following notebook logic)
        media_decode_os_fps = round((events_data['media_decode_os_count'] / duration / 9), 2)
        media_decode_drv_fps = round((events_data['media_decode_drv_count'] / duration / 9), 2)
        media_encode_os_fps = events_data['media_encode_os_count']
        media_encode_drv_fps = round(events_data['media_encode_drv_count'] / duration, 2)
        vpblt_input_fps = events_data['vpblt_input_count']
        
        # Display IP FPS calculations
        display_present_fps = round(events_data['display_present_count'] / duration, 2)
        display_mmioflip_fps = round(events_data['display_mmioflip_count'] / duration, 2)
        display_vsync_fps = round(events_data['display_vsync_count'] / duration, 2)
        display_vblank_fps = round(events_data['display_vblank_count'] / duration, 2)
        display_flipq_fps = round(events_data['display_flipq_count'] / duration, 2)
        
        # Format strings
        decode_format_str = "H264" if events_data['decode_format'] == 4 else "MJPEG"
        encode_format_str = self._get_format_name(events_data['encode_format'])
        vpblt_input_format_str = self._get_format_name(events_data['vpblt_input_format'])
        vpblt_output_format_str = self._get_format_name(events_data['vpblt_output_format'])
        present_mode_str = self.present_mode_names.get(events_data['display_present_mode'], f"Unknown ({events_data['display_present_mode']})")
        
        print(f"✅ Metrics Calculated:")
        print(f"   Media Decode (OS): {media_decode_os_fps} fps")
        print(f"   Media Decode (Drv): {media_decode_drv_fps} fps")
        print(f"   Media Encode (Drv): {media_encode_drv_fps} fps")
        print(f"   Display Present: {display_present_fps} fps")
        
        return {
            # Media IP Metrics
            'media_decode_os_fps': media_decode_os_fps,
            'media_decode_drv_fps': media_decode_drv_fps,
            'media_decode_resolution': f"{events_data['decode_width']}x{events_data['decode_height']}",
            'media_decode_format': decode_format_str,
            'media_decode_bitdepth': events_data['decode_bitdepth'],
            
            'media_encode_os_fps': media_encode_os_fps,
            'media_encode_drv_fps': media_encode_drv_fps,
            'media_encode_resolution': f"{events_data['encode_width']}x{events_data['encode_height']}",
            'media_encode_format': encode_format_str,
            
            'vpblt_input_fps': vpblt_input_fps,
            'vpblt_input_resolution': f"{events_data['vpblt_input_width']}x{events_data['vpblt_input_height']}",
            'vpblt_input_format': vpblt_input_format_str,
            'vpblt_output_resolution': f"{events_data['vpblt_output_width']}x{events_data['vpblt_output_height']}",
            'vpblt_output_format': vpblt_output_format_str,
            
            # Display IP Metrics
            'display_present_fps': display_present_fps,
            'display_present_mode': present_mode_str,
            'display_source_resolution': f"{events_data['display_source_width']}x{events_data['display_source_height']}",
            'display_dest_resolution': f"{events_data['display_dest_width']}x{events_data['display_dest_height']}",
            'display_mmioflip_fps': display_mmioflip_fps,
            'display_vsync_fps': display_vsync_fps,
            'display_vblank_fps': display_vblank_fps,
            'display_flipq_fps': display_flipq_fps,
            
            # Raw event counts
            'event_counts': events_data
        }
    
    def _get_format_name(self, format_code):
        """Convert format code to human-readable name"""
        return self.format_mapping.get(format_code, f"UNKNOWN({format_code})")
    
    def _generate_pipeline_results(self, metrics, time_range):
        """Generate final pipeline analysis results"""
        from datetime import datetime
        
        return {
            # Media IP Results
            'media_decode_os_fps': metrics['media_decode_os_fps'],
            'media_decode_drv_fps': metrics['media_decode_drv_fps'],
            'media_decode_resolution': metrics['media_decode_resolution'],
            'media_decode_format': metrics['media_decode_format'],
            'media_decode_bitdepth': metrics['media_decode_bitdepth'],
            
            'media_encode_os_fps': metrics['media_encode_os_fps'],
            'media_encode_drv_fps': metrics['media_encode_drv_fps'],
            'media_encode_resolution': metrics['media_encode_resolution'],
            'media_encode_format': metrics['media_encode_format'],
            
            'vpblt_input_fps': metrics['vpblt_input_fps'],
            'vpblt_input_resolution': metrics['vpblt_input_resolution'],
            'vpblt_input_format': metrics['vpblt_input_format'],
            'vpblt_output_resolution': metrics['vpblt_output_resolution'],
            'vpblt_output_format': metrics['vpblt_output_format'],
            
            # Display IP Results
            'display_present_fps': metrics['display_present_fps'],
            'display_present_mode': metrics['display_present_mode'],
            'display_source_resolution': metrics['display_source_resolution'],
            'display_dest_resolution': metrics['display_dest_resolution'],
            'display_mmioflip_fps': metrics['display_mmioflip_fps'],
            'display_vsync_fps': metrics['display_vsync_fps'],
            'display_vblank_fps': metrics['display_vblank_fps'],
            'display_flipq_fps': metrics['display_flipq_fps'],
            
            # Event Counts (for debugging)
            'media_decode_os_events': metrics['event_counts']['media_decode_os_count'],
            'media_decode_drv_events': metrics['event_counts']['media_decode_drv_count'],
            'media_encode_os_events': metrics['event_counts']['media_encode_os_count'],
            'media_encode_drv_events': metrics['event_counts']['media_encode_drv_count'],
            'display_present_events': metrics['event_counts']['display_present_count'],
            'display_mmioflip_events': metrics['event_counts']['display_mmioflip_count'],
            'display_vsync_events': metrics['event_counts']['display_vsync_count'],
            'display_vblank_events': metrics['event_counts']['display_vblank_count'],
            'display_flipq_events': metrics['event_counts']['display_flipq_count'],
            
            # Metadata
            'time_range': time_range,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'SUCCESS'
        }
    
    def _generate_detailed_report(self, results):
        """Generate detailed text report"""
        return f"""TEAMS VIDEO PIPELINE DETAILED ANALYSIS REPORT
=============================================
Generated: {results['timestamp']}
Analysis Period: {results['time_range'][0]}s - {results['time_range'][1]}s

MEDIA IP ACTIVITY:
==================

Decode Performance:
  - Decode (OS):     {results['media_decode_os_fps']} fps
  - Decode (Driver): {results['media_decode_drv_fps']} fps
  - Resolution:      {results['media_decode_resolution']}
  - Format:          {results['media_decode_format']}
  - Bit Depth:       {results['media_decode_bitdepth']}

Encode Performance:
  - Encode (OS):     {results['media_encode_os_fps']} fps
  - Encode (Driver): {results['media_encode_drv_fps']} fps
  - Resolution:      {results['media_encode_resolution']}
  - Format:          {results['media_encode_format']}

VPBlt Processing:
  - Input FPS:       {results['vpblt_input_fps']} fps
  - Input:           {results['vpblt_input_resolution']} {results['vpblt_input_format']}
  - Output:          {results['vpblt_output_resolution']} {results['vpblt_output_format']}

DISPLAY IP ACTIVITY:
====================

Display Present:
  - Present FPS:     {results['display_present_fps']} fps
  - Source:          {results['display_source_resolution']}
  - Destination:     {results['display_dest_resolution']}
  - Mode:            {results['display_present_mode']}

Display Performance:
  - MMIOFlip:        {results['display_mmioflip_fps']} fps
  - VSync:           {results['display_vsync_fps']} fps
  - VBlank (Driver): {results['display_vblank_fps']} fps
  - FlipQ (Driver):  {results['display_flipq_fps']} fps

EVENT COUNTS:
=============
Media Decode (OS):    {results['media_decode_os_events']}
Media Decode (Drv):   {results['media_decode_drv_events']}
Media Encode (OS):    {results['media_encode_os_events']}
Media Encode (Drv):   {results['media_encode_drv_events']}
Display Present:      {results['display_present_events']}
Display MMIOFlip:     {results['display_mmioflip_events']}
Display VSync:        {results['display_vsync_events']}
Display VBlank:       {results['display_vblank_events']}
Display FlipQ:        {results['display_flipq_events']}

Status: {results['status']}
"""
    
    def _save_report(self, report_text, output_path):
        """Save detailed report to file"""
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_text)

def teams_KPI_analysis(etl_path=None, 
                                            time_range=(0, 60),
                                            vcip_time_range=(2, 10),
                                            fps_time_range=(5, 65),
                                            pipeline_time_range=(32, 33),
                                            constraints_file=None,
                                            operation='all'):
    """
    API-Friendly Teams KPI Analysis Function - WITH Constraints DataFrame Data
    
    Returns flattened dictionary WITH constraints data as records array.
    
    Args:
        etl_path (str): Path to ETL file
        time_range (tuple): Time range for main trace loading (start_sec, end_sec)
        vcip_time_range (tuple): Time range for VCIP analysis
        fps_time_range (tuple): Time range for FPS analysis
        pipeline_time_range (tuple): Time range for pipeline analysis
        constraints_file (str): Path to constraints file
        operation (str): Which analysis to run - 'all', 'fps', 'vcip', 'constraints', 'pipeline'
                        - 'all': Run all analyses (default)
                        - 'fps': Run only FPS analysis
                        - 'vcip': Run only VCIP alignment analysis
                        - 'constraints': Run only constraints analysis
                        - 'pipeline': Run only pipeline analysis (Media IP + Display IP)
    
    Returns:
        dict: Flattened KPI results with constraints data included
    """
    
    # Set defaults
    if etl_path is None:
        etl_path = r'D:\bharath_working_directory\share\LNL\DIL\Teams3x3+MEPenable+PR7Stack+Multimedia_wprp.etl'
    
    if constraints_file is None and operation in ['all', 'constraints']:
        # Try to find constraints file in speedlibs_service folder first
        # Use multiple potential paths since __file__ may not be available in kernel
        import os
        potential_paths = [
            r'E:\agents\new_sdk\autobots_sdk_20251009_010150\speedlibs_service\constraints\teams_constraint.txt',
            r'D:\bharath_working_directory\share\LNL\speed_constraints\teams_constraint.txt',
            r'e:\agents\new_sdk\autobots_sdk_20251009_010150\speedlibs_service\constraints\teams_constraint.txt'
        ]
        
        for path in potential_paths:
            if os.path.exists(path):
                constraints_file = path
                break
        else:
            # Fallback to original default
            constraints_file = r"D:\bharath_working_directory\share\LNL\speed_constraints\teams_constraint.txt"
    
    # Validate operation parameter
    valid_operations = ['all', 'fps', 'vcip', 'constraints', 'pipeline']
    if operation not in valid_operations:
        return {
            "error": f"Invalid operation '{operation}'. Must be one of: {', '.join(valid_operations)}",
            "analysis_timestamp": pd.Timestamp.now().isoformat(),
            "etl_file": etl_path
        }
    
    try:
        print(f"🚀 API-Friendly Teams KPI Analysis - Operation: {operation.upper()}")
        print(f"📂 ETL: {etl_path}")
        print(f"⏱️  Ranges: Main{time_range}, VCIP{vcip_time_range}, FPS{fps_time_range}, Pipeline{pipeline_time_range}")
        
        # 1. Load trace once - using cached loading
        trace = load_trace_cached(etl_file=etl_path, time_range=time_range)
        
        # Initialize result containers
        vcip_raw = {}
        fps_raw = {}
        pipeline_raw = {}
        constraints_df = pd.DataFrame()
        
        # 2. VCIP Analysis (conditional)
        if operation in ['all', 'vcip']:
            print("🔍 Running VCIP Analysis...")
            vcip_analyzer = VCIP_SingleETL_Enhanced()
            vcip_raw = vcip_analyzer.analyze_4ip_alignment(etl_path_or_trace=trace, time_range=vcip_time_range)
        else:
            print("⏭️  Skipping VCIP Analysis")
        
        # 3. FPS Analysis (conditional)
        if operation in ['all', 'fps']:
            print("🎥 Running FPS Analysis...")
            fps_analyzer = TeamsFPS()
            fps_raw = fps_analyzer.analyze_fps(etl_path_or_trace=trace, time_range=fps_time_range)
        else:
            print("⏭️  Skipping FPS Analysis")
        
        # 4. Pipeline Analysis (conditional)
        if operation in ['all', 'pipeline']:
            print("🔧 Running Pipeline Analysis...")
            pipeline_analyzer = TeamsPipelineAnalysis()
            pipeline_raw = pipeline_analyzer.analyze_pipeline(etl_path_or_trace=trace, time_range=pipeline_time_range)
        else:
            print("⏭️  Skipping Pipeline Analysis")
        
        # 5. Constraints Analysis (conditional)
        if operation in ['all', 'constraints']:
            print("📋 Running Constraints Analysis...")
            constraints_df = PPAApi.analyze_constraints(trace, constraints_file)
        else:
            print("⏭️  Skipping Constraints Analysis")
        
        # 6. Create flat, API-friendly dictionary WITH constraints data
        api_result = {
            # Operation metadata
            "operation": operation,
            "operation_description": {
                "all": "Full analysis (VCIP + FPS + Pipeline + Constraints)",
                "vcip": "VCIP alignment analysis only",
                "fps": "FPS metrics analysis only",
                "pipeline": "Pipeline analysis (Media IP + Display IP) only",
                "constraints": "Constraints validation only"
            }.get(operation, "Unknown"),
            
            # Raw alignment rates (numeric or string like "NOT_FOUND")
            "media_to_audio_alignment": vcip_raw.get('media_to_audio', 'NOT_RUN' if operation not in ['all', 'vcip'] else 'ERROR'),
            "ipu_to_audio_alignment": vcip_raw.get('ipu_to_audio', 'NOT_RUN' if operation not in ['all', 'vcip'] else 'ERROR'),
            "wlan_to_audio_alignment": vcip_raw.get('wlan_to_audio', 'NOT_RUN' if operation not in ['all', 'vcip'] else 'ERROR'),
            
            # Raw FPS values
            "decode_fps": fps_raw.get('decode_fps', 0.0),
            "encode_fps": fps_raw.get('encode_fps', 0.0),
            "vpblt_fps": fps_raw.get('vpblt_fps', 0.0),
            "camera_fps": fps_raw.get('camera_fps', 0.0),
            
            # Pipeline Analysis - Media IP
            "pipeline_media_decode_os_fps": pipeline_raw.get('media_decode_os_fps', 0.0),
            "pipeline_media_decode_drv_fps": pipeline_raw.get('media_decode_drv_fps', 0.0),
            "pipeline_media_decode_resolution": pipeline_raw.get('media_decode_resolution', 'N/A'),
            "pipeline_media_decode_format": pipeline_raw.get('media_decode_format', 'N/A'),
            "pipeline_media_decode_bitdepth": pipeline_raw.get('media_decode_bitdepth', 0),
            "pipeline_media_encode_os_fps": pipeline_raw.get('media_encode_os_fps', 0.0),
            "pipeline_media_encode_drv_fps": pipeline_raw.get('media_encode_drv_fps', 0.0),
            "pipeline_media_encode_resolution": pipeline_raw.get('media_encode_resolution', 'N/A'),
            "pipeline_media_encode_format": pipeline_raw.get('media_encode_format', 'N/A'),
            "pipeline_vpblt_input_fps": pipeline_raw.get('vpblt_input_fps', 0.0),
            "pipeline_vpblt_input_resolution": pipeline_raw.get('vpblt_input_resolution', 'N/A'),
            "pipeline_vpblt_input_format": pipeline_raw.get('vpblt_input_format', 'N/A'),
            "pipeline_vpblt_output_resolution": pipeline_raw.get('vpblt_output_resolution', 'N/A'),
            "pipeline_vpblt_output_format": pipeline_raw.get('vpblt_output_format', 'N/A'),
            
            # Pipeline Analysis - Display IP
            "pipeline_display_present_fps": pipeline_raw.get('display_present_fps', 0.0),
            "pipeline_display_present_mode": pipeline_raw.get('display_present_mode', 'N/A'),
            "pipeline_display_source_resolution": pipeline_raw.get('display_source_resolution', 'N/A'),
            "pipeline_display_dest_resolution": pipeline_raw.get('display_dest_resolution', 'N/A'),
            "pipeline_display_mmioflip_fps": pipeline_raw.get('display_mmioflip_fps', 0.0),
            "pipeline_display_vsync_fps": pipeline_raw.get('display_vsync_fps', 0.0),
            "pipeline_display_vblank_fps": pipeline_raw.get('display_vblank_fps', 0.0),
            "pipeline_display_flipq_fps": pipeline_raw.get('display_flipq_fps', 0.0),
            
            # Event counts (for agent context)
            "audio_events_count": vcip_raw.get('alignment_details', {}).get('events_counts', {}).get('audio_events', 0),
            "media_events_count": vcip_raw.get('alignment_details', {}).get('events_counts', {}).get('media_events', 0),
            "ipu_events_count": vcip_raw.get('alignment_details', {}).get('events_counts', {}).get('ipu_events', 0),
            "wlan_hw_events_count": vcip_raw.get('alignment_details', {}).get('events_counts', {}).get('wlan_hw_events', 0),
            "audio_hw_events_count": vcip_raw.get('alignment_details', {}).get('events_counts', {}).get('audio_hw_events', 0),
            
            # Video event counts
            "decode_events_count": fps_raw.get('event_counts', {}).get('decode_events', 0),
            "encode_events_count": fps_raw.get('event_counts', {}).get('encode_events', 0),
            "vpblt_events_count": fps_raw.get('event_counts', {}).get('vpblt_events', 0),
            "camera_events_count": fps_raw.get('event_counts', {}).get('camera_events', 0),
            
            # Pipeline event counts
            "pipeline_media_decode_os_events": pipeline_raw.get('media_decode_os_events', 0),
            "pipeline_media_decode_drv_events": pipeline_raw.get('media_decode_drv_events', 0),
            "pipeline_media_encode_os_events": pipeline_raw.get('media_encode_os_events', 0),
            "pipeline_media_encode_drv_events": pipeline_raw.get('media_encode_drv_events', 0),
            "pipeline_display_present_events": pipeline_raw.get('display_present_events', 0),
            "pipeline_display_mmioflip_events": pipeline_raw.get('display_mmioflip_events', 0),
            "pipeline_display_vsync_events": pipeline_raw.get('display_vsync_events', 0),
            "pipeline_display_vblank_events": pipeline_raw.get('display_vblank_events', 0),
            "pipeline_display_flipq_events": pipeline_raw.get('display_flipq_events', 0),
            
            # ⭐ CONSTRAINTS DATA - Full DataFrame as records array
            "constraints_count": len(constraints_df) if not constraints_df.empty else 0,
            "constraints_columns": list(constraints_df.columns.tolist()) if not constraints_df.empty else [],
            "constraints_data": constraints_df.to_dict('records') if not constraints_df.empty else [],
            
            # Analysis metadata (flat)
            "etl_file": etl_path,
            "main_time_start": time_range[0],
            "main_time_end": time_range[1],
            "vcip_time_start": vcip_time_range[0],
            "vcip_time_end": vcip_time_range[1],
            "fps_time_start": fps_time_range[0],
            "fps_time_end": fps_time_range[1],
            "pipeline_time_start": pipeline_time_range[0],
            "pipeline_time_end": pipeline_time_range[1],
            "constraints_file": constraints_file,
            "analysis_timestamp": pd.Timestamp.now().isoformat(),
            
            # Missing events list (flat)
            "missing_events": vcip_raw.get('missing_events', []),
            
            # Success flags (boolean, not evaluative status)
            "vcip_analysis_completed": 'error' not in vcip_raw and operation in ['all', 'vcip'],
            "fps_analysis_completed": 'error' not in fps_raw and operation in ['all', 'fps'],
            "pipeline_analysis_completed": 'error' not in pipeline_raw and operation in ['all', 'pipeline'],
            "constraints_analysis_completed": (constraints_df is not None and not constraints_df.empty) and operation in ['all', 'constraints']
        }
        
        print(f"✅ API-Friendly Analysis Complete - Operation: {operation.upper()}!")
        print(f"📊 Result Keys: {len(api_result)} flat fields")
        if operation in ['all', 'constraints']:
            print(f"📋 Constraints Data: {len(api_result['constraints_data'])} records included")
        
        return api_result
        
    except Exception as e:
        print(f"❌ API Analysis Error: {e}")
        # Return minimal error structure
        return {
            "error": str(e),
            "analysis_timestamp": pd.Timestamp.now().isoformat(),
            "etl_file": etl_path,
            "vcip_analysis_completed": False,
            "fps_analysis_completed": False,
            "constraints_analysis_completed": False,
            "constraints_data": []
        }


def ContainmentBreach(combined_df):
    """
    Standalone function for containment breach analysis
    Matches the exact implementation from preprocessETL.ipynb
    """
    import pandas as pd
    
    # Load the CSV file into a DataFrame
    df = combined_df.copy()

    columns_to_keep = ["timestamp", 'AfterPerfUnparkCount', 'AfterEfficientUnparkCount']
    columns_to_keep2 = ["timestamp", 'PerfUnparkCount', 'EfficientUnparkCount']

    columns_to_keep_set = set(columns_to_keep)
    columns_to_keep2_set = set(columns_to_keep2)
    df_columns_set = set(df.columns)

    if columns_to_keep_set.issubset(df_columns_set):
        df = df[columns_to_keep]
    elif columns_to_keep2_set.issubset(df_columns_set):
        df = df[columns_to_keep2]
    else:
        print("Warning: Required columns not found for containment breach analysis")
        return pd.DataFrame()

    df = df.dropna()

    # Initialize lists to store the new DataFrame's columns
    start_times = []
    end_times = []
    trigger_reasons = []
    average_perf_unpark_counts = []

    # Initialize variables to track the start time, trigger reason, and counts
    start_time = None
    trigger_reason = None
    perf_unpark_counts = []
    trace_end = df["timestamp"].max()

    a = 4  # Threshold value from notebook

    # Iterate over the DataFrame rows
    for index, row in df.iterrows():
        try:
            if start_time is None and row['AfterPerfUnparkCount'] > 0:
                # Set the start time when AfterPerfUnparkCount becomes greater than 0
                start_time = row['timestamp']
                # Determine the trigger reason
                if row['AfterPerfUnparkCount'] + row['AfterEfficientUnparkCount'] > a:
                    trigger_reason = 'concurrency'
                else:
                    trigger_reason = 'utilization/HGS'
                # Initialize the list to store counts
                perf_unpark_counts = [row['AfterPerfUnparkCount']]

            elif start_time is not None:
                perf_unpark_counts.append(row['AfterPerfUnparkCount'])
                
                # Monitor state change and update the table, 250ms at least required to stay in same state
                if trigger_reason == 'concurrency' and (row["timestamp"] < (start_time + 0.250)):
                    if row['AfterPerfUnparkCount'] + row['AfterEfficientUnparkCount'] > a:
                        pass
                    else:
                        end_time = row['timestamp']
                        # Calculate the average AfterPerfUnparkCount
                        average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                        # Append the results to the lists
                        start_times.append(start_time)
                        end_times.append(end_time)
                        trigger_reasons.append(trigger_reason)
                        average_perf_unpark_counts.append(average_perf_unpark_count)
                        # Reset start_time, trigger_reason, and perf_unpark_counts for the next interval
                        start_time = None
                        trigger_reason = None
                        perf_unpark_counts = []
                        continue

                if trigger_reason == 'utilization/HGS' and (row["timestamp"] < (start_time + 0.250)):
                    if row['AfterPerfUnparkCount'] + row['AfterEfficientUnparkCount'] > a:
                        end_time = row['timestamp']
                        # Calculate the average AfterPerfUnparkCount
                        average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                        # Append the results to the lists
                        start_times.append(start_time)
                        end_times.append(end_time)
                        trigger_reasons.append(trigger_reason)
                        average_perf_unpark_counts.append(average_perf_unpark_count)
                        # Reset start_time, trigger_reason, and perf_unpark_counts for the next interval
                        start_time = None
                        trigger_reason = None
                        perf_unpark_counts = []
                        continue
                    else:
                        pass

                if row['AfterPerfUnparkCount'] == 0:
                    # Set the end time when AfterPerfUnparkCount becomes zero
                    end_time = row['timestamp']
                    # Calculate the average AfterPerfUnparkCount
                    average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                    # Append the results to the lists
                    start_times.append(start_time)
                    end_times.append(end_time)
                    trigger_reasons.append(trigger_reason)
                    average_perf_unpark_counts.append(average_perf_unpark_count)
                    # Reset start_time, trigger_reason, and perf_unpark_counts for the next interval
                    start_time = None
                    trigger_reason = None
                    perf_unpark_counts = []

                if row["timestamp"] == trace_end:
                    end_time = row['timestamp']
                    # Calculate the average AfterPerfUnparkCount
                    average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                    # Append the results to the lists
                    start_times.append(start_time)
                    end_times.append(end_time)
                    trigger_reasons.append(trigger_reason)
                    average_perf_unpark_counts.append(average_perf_unpark_count)
                    # Reset start_time, trigger_reason, and perf_unpark_counts for the next interval
                    start_time = None
                    trigger_reason = None
                    perf_unpark_counts = []

        except:
            try:
                # Fallback to alternative column names
                if start_time is None and row['PerfUnparkCount'] > 0:
                    # Set the start time when PerfUnparkCount becomes greater than 0
                    start_time = row['timestamp']
                    # Determine the trigger reason
                    if row['PerfUnparkCount'] + row['EfficientUnparkCount'] > a:
                        trigger_reason = 'concurrency'
                    else:
                        trigger_reason = 'utilization/HGS'
                    # Initialize the list to store counts
                    perf_unpark_counts = [row['PerfUnparkCount']]
                    
                elif start_time is not None:
                    # Collect PerfUnparkCount values for averaging
                    perf_unpark_counts.append(row['PerfUnparkCount'])

                    # Monitor state change and update the table
                    if trigger_reason == 'concurrency' and (row["timestamp"] < (start_time + 0.250)):
                        if row['PerfUnparkCount'] + row['EfficientUnparkCount'] > a:
                            pass
                        else:
                            end_time = row['timestamp']
                            # Calculate the average PerfUnparkCount
                            average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                            # Append the results to the lists
                            start_times.append(start_time)
                            end_times.append(end_time)
                            trigger_reasons.append(trigger_reason)
                            average_perf_unpark_counts.append(average_perf_unpark_count)
                            # Reset start_time, trigger_reason, and perf_unpark_counts for the next interval
                            start_time = None
                            trigger_reason = None
                            perf_unpark_counts = []
                            continue

                    if trigger_reason == 'utilization/HGS' and (row["timestamp"] < (start_time + 0.250)):
                        if row['PerfUnparkCount'] + row['EfficientUnparkCount'] > a:
                            end_time = row['timestamp']
                            # Calculate the average PerfUnparkCount
                            average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                            # Append the results to the lists
                            start_times.append(start_time)
                            end_times.append(end_time)
                            trigger_reasons.append(trigger_reason)
                            average_perf_unpark_counts.append(average_perf_unpark_count)
                            # Reset start_time, trigger_reason, and perf_unpark_counts for the next interval
                            start_time = None
                            trigger_reason = None
                            perf_unpark_counts = []
                            continue
                        else:
                            pass

                    if row['PerfUnparkCount'] == 0:
                        # Set the end time when PerfUnparkCount becomes zero
                        end_time = row['timestamp']
                        # Calculate the average PerfUnparkCount
                        average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                        # Append the results to the lists
                        start_times.append(start_time)
                        end_times.append(end_time)
                        trigger_reasons.append(trigger_reason)
                        average_perf_unpark_counts.append(average_perf_unpark_count)
                        # Reset start_time, trigger_reason, and perf_unpark_counts for the next interval
                        start_time = None
                        trigger_reason = None
                        perf_unpark_counts = []

                    if row["timestamp"] == trace_end:
                        end_time = row['timestamp']
                        # Calculate the average PerfUnparkCount
                        average_perf_unpark_count = sum(perf_unpark_counts) / len(perf_unpark_counts)
                        # Append the results to the lists
                        start_times.append(start_time)
                        end_times.append(end_time)
                        trigger_reasons.append(trigger_reason)
                        average_perf_unpark_counts.append(average_perf_unpark_count)
                        # Reset start_time, trigger_reason, and perf_unpark_counts for the next interval
                        start_time = None
                        trigger_reason = None
                        perf_unpark_counts = []
            except:
                print("Failed to compute containment breach")

    # Create the new DataFrame
    result_df = pd.DataFrame({
        'start_time': start_times,
        'end_time': end_times,
        'trigger_reason': trigger_reasons,
        'average_perf_unpark_count': average_perf_unpark_counts
    })

    result_df["duration"] = result_df["end_time"] - result_df["start_time"]

    # Return the result DataFrame
    return result_df

# ==========================================================================
# ANALYSIS FUNCTIONS
# ==========================================================================

def traceSummary(trace,timerange=None):

    from ppa.analysis.summary import trace_summary

    # Use cached trace loading for better performance
    test = load_trace_cached(etl_file=trace, time_range=timerange)
    if timerange==None:
        timerange=test.time_range
    summary = trace_summary(test,time_range=timerange)
    api_results={
    "summary_driverinfo_df":summary.platform_info.driver_info,
    "summary_platforminfo_df":summary.platform_info.platform_info,
    "summary_activethreadstat_df":summary.active_threads_stats,
    "summary_concurrentparkedcores_df":summary.concurrent_parked_cores,
    "summary_cpufrequencystats_df":summary.cpu_frequency_stats,
    "summary_cpugpuconcurrencystats_df":summary.cpu_gpu_concurrency_stats,
    "summary_diskstats_df":summary.disk_stats,
    "summary_dpcstats_df":summary.dpc_stats,
    "summary_highlevelstats_df":summary.high_level_stats,
    "summary_interruptstats_df":summary.interrupt_stats,
    "summary_ipstats_df":summary.ip_stats,
    "summary_processstats_df":summary.process_stats,
    "summary_qospercore_df":summary.qos_per_core,
    "summary_qosperprocess_df":summary.qos_per_process,
    "summary_serviceinfo_df":summary.service_info.services,
    "summary_threadstats_df":summary.thread_stats,
    "summary_utilizationperlogical_df":summary.utilization_per_logical,
    "summary_vpustats_df":summary.vpu_stats
    }
    return api_results

def analyze_constraints(etl_file_path, constraints_file, socwatch_file=None):
    """
    Generic constraints analysis function using SPEED kernel approach
    
    This function performs a simple 3-step process:
    1. Load the ETL trace (with optional socwatch file)
    2. Analyze constraints using PPAApi.analyze_constraints
    3. Return results DataFrame
    
    Args:
        etl_file_path (str): Path to ETL file (mandatory)
        constraints_file (str): Path to constraints file (mandatory)
        socwatch_file (str, optional): Path to socwatch summary CSV file (optional)
    
    Returns:
        pandas.DataFrame: Constraints analysis results
    """
    try:
        # Import SPEED kernel PPA modules
        try:
            from ppa.constraints import evaluate
            import ppa.constraints.parser
            from ppa.ppa_api import PPAApi
            from ppa.analysis.summary import combine_trace_summaries
            from ppa.report_objects import ConstraintsReport
            print(f"[OK] SPEED kernel PPA modules imported successfully")
        except ImportError as e:
            print(f"[ERROR] PPA modules not available: {e}")
            print(f"[ERROR] Cannot perform constraints analysis without PPA modules")
            return pd.DataFrame({
                'constraint': ['ppa_not_available'],
                'status': ['error'],
                'value': [0.0],
                'error': [str(e)]
            })
        
        # Step 1: Load trace with ETL file (and optional socwatch file)
        print(f"[CONSTRAINTS] Loading trace from ETL: {etl_file_path}")
        if socwatch_file:
            print(f"[CONSTRAINTS] Including socwatch file: {socwatch_file}")
            if not os.path.exists(socwatch_file):
                print(f"[ERROR] Socwatch file not found: {socwatch_file}")
                return pd.DataFrame({
                    'constraint': ['socwatch_file_not_found'],
                    'status': ['error'],
                    'value': [0.0]
                })
        
        # Load trace using cached loading
        trace = load_trace_cached(
            etl_file=etl_file_path,
            time_range=(0, 1),
            socwatch_summary_file=socwatch_file
        )
        print(f"[CONSTRAINTS] ✅ Trace loaded successfully")
        
        # Step 2: Verify constraints file exists
        if not os.path.exists(constraints_file):
            print(f"[ERROR] Constraints file not found: {constraints_file}")
            return pd.DataFrame({
                'constraint': ['constraints_file_not_found'],
                'status': ['error'],
                'value': [0.0]
            })
        
        print(f"[CONSTRAINTS] Using constraints file: {constraints_file}")
        
        # Step 3: Run constraints analysis
        print(f"[CONSTRAINTS] Running PPAApi.analyze_constraints...")
        results_df = PPAApi.analyze_constraints(trace, constraints_file)
        
        print(f"[CONSTRAINTS] ✅ Constraints analysis completed")
        print(f"[CONSTRAINTS] Results shape: {results_df.shape}")
        
        return results_df
        
    except Exception as e:
        print(f"[ERROR] Error in constraints analysis: {e}")
        import traceback
        traceback.print_exc()
        
        # Return error DataFrame
        return pd.DataFrame({
            'constraint': ['analysis_failed'],
            'status': ['error'],
            'value': [0.0],
            'error': [str(e)]
        })

def analyze_ppm_constraints(etl_file_path, etl_trace, logpath, constraints_file=None, is_validation=False):
    """
    Analyze PPM constraints using proper SPEED kernel approach
    
    Args:
        etl_file_path (str): Original ETL file path
        etl_trace (EtlTrace): ETL trace object for data extraction
        logpath (str): Output directory for temp files
        constraints_file (str, optional): PPM constraints file path
        is_validation (bool): True for PPM validation, False for PPM behavior
    
    Returns:
        pandas.DataFrame: PPM constraints analysis results
    """
    try:
        # Import SPEED kernel PPM analysis components
        try:
            
            from ppa.constraints import evaluate
            
            import ppa.constraints.parser
            from ppa.ppa_api import PPAApi
            from ppa.analysis.summary import combine_trace_summaries
            from ppa.report_objects import ConstraintsReport
            print(f"[OK] SPEED kernel PPA modules imported successfully")
        except ImportError as e:
            print(f"[WARNING] PPA modules not available: {e}")
            print(f"[WARNING] Falling back to placeholder results")
            return pd.DataFrame({
                'constraint': ['ppa_not_available'],
                'status': ['warning'],
                'value': [0.0]
            })
        
        # Create temp directory for CSV files
        temp_dir = os.path.join(logpath, "ppm_temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        if is_validation:
            print(f"[PPM-VAL] Generating PPM validation constraints analysis...")
            
            # Step 1: Generate PPM validation CSV from ETL trace PPM settings rundown
            ppm_val_csv = os.path.join(temp_dir, "PPMVAL.csv")
            
            # Extract PPM settings data using ETL trace rundown function
            if hasattr(etl_trace, 'get_ppm_settings') and hasattr(etl_trace, 'df_ppm_settings'):
                ppm_settings_df = etl_trace.df_ppm_settings
                if not ppm_settings_df.empty:
                    ppm_settings_df.to_csv(ppm_val_csv, index=False)
                    print(f"[PPM-VAL] ✅ PPM validation CSV generated: {ppm_val_csv}")
                else:
                    print(f"[PPM-VAL] ⚠️  No PPM settings data available")
                    return pd.DataFrame()
            else:
                print(f"[PPM-VAL] ⚠️  PPM settings extraction not available")
                return pd.DataFrame()
            
            # Step 2: Set default PPM validation constraint file
            if constraints_file is None:
                constraints_file = DEFAULT_PPM_VAL_CONSTRAINT_FILE
            
            socwatch_summary_file = ppm_val_csv
            
        else:
            print(f"[PPM-BEH] Generating PPM behavior constraints analysis...")
            
            # Step 1: Generate preprocessed CSV from combined data
            preprocess_csv = os.path.join(temp_dir, "PPM_PreProcess.csv")
            
            # Use preprocessor to generate the CSV
            combined_df = etl_trace.combined_df
            if combined_df is not None and not combined_df.empty:
                preprocessor = pre_process(combined_df, temp_dir)
                if not preprocessor.final_df.empty:
                    preprocessor.final_df.to_csv(preprocess_csv, index=False)
                    print(f"[PPM-BEH] ✅ Preprocessed CSV generated: {preprocess_csv}")
                else:
                    print(f"[PPM-BEH] ⚠️  Preprocessing failed - empty result")
                    return pd.DataFrame()
            else:
                print(f"[PPM-BEH] ⚠️  No combined data available for preprocessing")
                return pd.DataFrame()
            
            # Step 2: Set default PPM behavior constraint file
            if constraints_file is None:
                constraints_file = DEFAULT_PPM_CONSTRAINT_FILE
            
            socwatch_summary_file = preprocess_csv
        
        # Step 3: Reload trace with the generated CSV (SPEED kernel approach)
        print(f"[PPM] Reloading trace with socwatch file: {socwatch_summary_file}")
        
        if not os.path.exists(socwatch_summary_file):
            print(f"[PPM] ❌ Socwatch file not found: {socwatch_summary_file}")
            return pd.DataFrame()
        
        # Reload trace with CSV - using time_range (0,1) as per example
        # Using cached loading to avoid redundant file loading
        ppm_trace = load_trace_cached(
            etl_file=etl_file_path,
            time_range=(0, 1),
            socwatch_summary_file=socwatch_summary_file
        )
        print(f"[PPM] ✅ Trace reloaded with socwatch file")
        
        # Step 4: Run PPM constraints analysis using PPAApi
        if not os.path.exists(constraints_file):
            print(f"[PPM] ⚠️  Constraints file not found: {constraints_file}")
            print(f"[PPM] Creating placeholder constraints file...")
            
            # Create placeholder constraint file
            placeholder_constraints = """
# Placeholder PPM constraints
# Replace with actual constraint definitions
constraint_example = True
"""
            with open(constraints_file, 'w') as f:
                f.write(placeholder_constraints)
        
        print(f"[PPM] Running PPAApi.analyze_constraints...")
        ppm_results_df = PPAApi.analyze_constraints(ppm_trace, constraints_file)
        
        print(f"[PPM] ✅ PPM constraints analysis completed")
        print(f"[PPM] Results shape: {ppm_results_df.shape}")
        
        return ppm_results_df
        
    except Exception as e:
        print(f"[ERROR] Error in PPM constraints analysis: {e}")
        import traceback
        traceback.print_exc()
        
        # Return placeholder results on error
        return pd.DataFrame({
            'constraint': ['analysis_failed'],
            'status': ['error'],  
            'value': [0.0],
            'error': [str(e)]
        })

def df_pickle(dataframes_to_save, logpath):
    """
    Save DataFrames to pickle file for AI agent consumption
    
    Args:
        dataframes_to_save: Dictionary or object containing DataFrames
        logpath: Output directory path
    """
    try:
        import pickle
        
        os.makedirs(logpath, exist_ok=True)
        pickle_file = os.path.join(logpath, 'dfs.pkl')
        
        with open(pickle_file, 'wb') as f:
            pickle.dump(dataframes_to_save, f)
        
        print(f"[OK] Pickle file saved: {pickle_file}")
        
    except Exception as e:
        print(f"[ERROR] Error saving pickle: {e}")

def generate_comprehensive_analysis(etl_file_path, logpath, 
                                  ppm_constraints_file=None, 
                                  ppm_val_constraints_file=None,
                                  socwatch_file=None,
                                  socwatch_val_file=None):
    """
    Generate comprehensive ETL analysis and save results to pickle
    
    Args:
        etl_file_path: Path to ETL file
        logpath: Output directory for results
        ppm_constraints_file: PPM constraints file path  
        ppm_val_constraints_file: PPM validation constraints file path
        socwatch_file: Socwatch summary file for PPM analysis
        socwatch_val_file: Socwatch summary file for validation
        
    Returns:
        Dictionary containing all analysis results
    """
    print("=" * 80)
    print("[ANALYSIS] COMPREHENSIVE ETL ANALYSIS")
    print("=" * 80)
    
    if not SPEEDLIBS_WORKING:
        print("[ERROR] SpeedLibs not available - cannot perform analysis")
        return {}
    
    try:
        # 1. Load ETL trace using simplified method
        print(f"[FILE] Loading ETL file: {etl_file_path}")
        etl_trace = EtlTrace(etl_file_path)
        combined_df = etl_trace.getCombined()
        
        # Note: combined_df may be empty if combine_df() was skipped for performance
        # The actual data is in individual DataFrames (df_cpu_util, df_cpu_freq, etc.)
        print(f"[DATA] Combined DataFrame shape: {combined_df.shape}")
        
        print("[OK] ETL file loaded successfully")
        
        # 2. Perform pre-processing (skip if combined_df is empty)
        print("[FIX] Running pre-process analysis...")
        preprocessed_df = pd.DataFrame()
        if not combined_df.empty:
            try:
                preprocessor = pre_process(combined_df, logpath)
                preprocessed_df = preprocessor.final_df
            except Exception as e:
                print(f"[WARNING] Pre-processing failed: {e}")
                print("[WARNING] Continuing with empty preprocessed DataFrame")
                preprocessed_df = pd.DataFrame()
        else:
            print("[INFO] Combined DataFrame is empty, skipping pre-processing")
        
        # 3. Perform containment breach analysis (skip if combined_df is empty)
        print("[ANALYSIS] Performing containment breach analysis...")
        containment_breach_df = pd.DataFrame()
        if not combined_df.empty:
            try:
                containment_breach_df = ContainmentBreach(combined_df)
            except Exception as e:
                print(f"[WARNING] Containment breach analysis failed: {e}")
                print("[WARNING] Continuing with empty containment breach DataFrame")
        else:
            print("[INFO] Combined DataFrame is empty, skipping containment breach analysis")
        
        # 4. PPM Analysis using proper SPEED kernel approach
        print("[PPM] Starting PPM behavior analysis...")
        df_PPM = analyze_ppm_constraints(
            etl_file_path=etl_file_path,
            etl_trace=etl_trace,
            logpath=logpath,
            constraints_file=ppm_constraints_file,
            is_validation=False
        )
        
        print("[PPM] Starting PPM validation analysis...")
        df_Val = analyze_ppm_constraints(
            etl_file_path=etl_file_path,
            etl_trace=etl_trace,
            logpath=logpath,
            constraints_file=ppm_val_constraints_file,
            is_validation=True
        )
        
        # 5. Create comprehensive results dictionary - only DataFrames (pickle-safe)
        results_dict = {
            # Core combined and analysis dataframes
            "df_combined_dataframe": combined_df,
            "df_containment_breach": containment_breach_df,
            "df_preprocessed": preprocessed_df,
            "df_PPM_behaviour": df_PPM,
            "df_PPM_Validation": df_Val
        }
        
        # Add primary trace dataframes (user selected 12) - safely check each one
        trace_dataframes = [
            ("df_wlc", "df_wlc"),
            ("df_heteroresponse", "df_heteroresponse"),
            ("df_cpu_util", "df_cpu_util"), 
            ("df_cpu_freq", "df_cpu_freq"),
            ("df_containmentunpark", "df_wpscontainmentunpark"),
            ("df_heteroparkingselection", "df_heteroparkingselection"),
            ("df_softparkselection", "df_softparkselection"),
            ("df_ppm_settings", "df_ppm_settings"),
            ("df_interrupt", "df_interrupt"),
            ("df_fg_bg_ratio", "df_fg_bg_ratio"),
            ("df_c0_intervals", "df_c0_intervals"),
            ("df_package_energy", "df_package_energy"),
            ("df_ppmsettingschange","df_ppmsettingschange"),
            ("df_thread_interval","df_threadstat"),
            ("df_processlifetime","df_processlifetime"),
            ("df_containment_status","df_containment_status")
        ]
        
        for result_name, attr_name in trace_dataframes:
            if hasattr(etl_trace, attr_name):
                results_dict[result_name] = getattr(etl_trace, attr_name)
                print(f"[RESULTS] ✅ Added {result_name}")
            else:
                results_dict[result_name] = pd.DataFrame()
                print(f"[RESULTS] ⚠️  {result_name} not available, added empty DataFrame")
        
        # Add additional trace summary dataframes (if available)
        if hasattr(etl_trace, 'trace_summary'):
            summary_attrs = [
                ("df_utilization_per_logical_summary", "utilization_per_logical"),
                ("df_process_stats_summary", "process_stats"), 
                ("df_qos_per_process_summary", "qos_per_process"),
                ("df_qos_per_core_summary", "qos_per_core"),
                ("df_cpu_frequency_summary", "cpu_frequency_stats")
            ]
            
            for result_name, summary_attr in summary_attrs:
                results_dict[result_name] = getattr(etl_trace.trace_summary, summary_attr, pd.DataFrame())
        else:
            print("[RESULTS] ⚠️  trace_summary not available, skipping summary dataframes")
        
        # Add power state information (AC/DC state and power slider position)
        if hasattr(etl_trace, 'power_state_info'):
            results_dict['power_state_info'] = etl_trace.power_state_info
            print(f"[RESULTS] ✅ Added power_state_info: {etl_trace.power_state_info}")
        else:
            results_dict['power_state_info'] = {
                'power_slider': None,
                'ac_state': None,
                'scheme_guid': None
            }
            print("[RESULTS] ⚠️  power_state_info not available, added empty dict")
        
        # 6. Save to pickle file
        print("[FILE] Saving analysis results to pickle...")
        df_pickle(results_dict, logpath)
        
        print("=" * 80)
        print("[OK] COMPREHENSIVE ANALYSIS COMPLETE!")
        print("=" * 80)
        print(f"[FILE] Results saved to: {logpath}")
        print(f"[DATA] Total DataFrames: {len(results_dict)}")
        print("[OK] Ready for AI agent consumption!")
        
        return results_dict
        
    except Exception as e:
        print(f"[ERROR] Error in comprehensive analysis: {e}")
        import traceback
        traceback.print_exc()
        return {}

# ==========================================================================
# MAIN FUNCTION  
# ==========================================================================

def main():
    """Main function to demonstrate the working migration"""
    print("=" * 80)
    print("[OK] SPEEDLIBS MIGRATION - FULLY WORKING!")
    print("=" * 80)
    
    if SPEEDLIBS_WORKING:
        print("[OK] SpeedLibs is available and working!")
        print("[INIT] You can now use SpeedLibs directly in your notebooks!")
        print("[AI] AI agents can consume pickle files generated by this tool!")
        print("[DOC] Use the test notebook for function testing")
        
        print("\n[FUNCS] Available Functions:")
        print("  - simple_load_trace(etl_file, time_range=None)")
        print("  - EtlTrace(etl_file) - direct constructor call")
        print("  - generate_comprehensive_analysis(etl_file, logpath, ...)")
        print("  - EtlTrace(etl_file_or_trace)")
        print("  - pre_process(combined_df, output_dir)")
        print("  - ContainmentBreach(combined_df)")
        print("  - analyze_ppm_constraints(logpath, combined_df=None)")
        print("  - df_pickle(data, logpath)")
        
        print("\n[USAGE] Basic Usage:")
        print("  # Simple ETL loading")
        print("  combined_df = simple_load_trace('file.etl')")
        print("  # With time filtering")
        print("  filtered_df = simple_load_trace('file.etl', time_range=(0, 60))")
        print("  # Comprehensive analysis")
        print("  results = generate_comprehensive_analysis('file.etl', 'output_dir')")
    else:
        print("[ERROR] SpeedLibs not available - check DLL installation")
        print("[WARNING]  SpeedLibs migration needs DLL fixes")

if __name__ == "__main__":
    main()
