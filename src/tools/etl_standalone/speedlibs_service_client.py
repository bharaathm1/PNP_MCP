#!/usr/bin/env python3
"""
SpeedLibs Service Integration for MCP Agent

This module provides integration functions for the MCP agent to communicate
with the SpeedLibs REST service running in Python 3.10.

FALLBACK MECHANISM:
When the REST service is unavailable, this client automatically falls back to
running standalone Python scripts via speed.exe, providing seamless operation
even when the service is busy or not running.
"""

import requests
import json
import time
import os
import subprocess
import pickle
import shutil
from typing import Dict, Any, Optional
from pathlib import Path

class SpeedLibsServiceClient:
    def __init__(self, base_url=None, enable_fallback=True, speed_exe_path=None,
                 standalone_scripts_dir=None, show_console=True):
        """
        show_console: When True (default), speed.exe runs in a new visible console
                      window so you can watch progress in real time.  Set to False
                      to run hidden (original behaviour, output captured silently).
        """
        # Determine port from environment variable or use default
        if base_url is None:
            port = os.environ.get("SPEEDLIBS_SERVICE_PORT", "8880")
            base_url = f"http://127.0.0.1:{port}"
        
        self.base_url = base_url
        # Proxy-bypass session: trust_env=False ignores system proxy settings
        # so localhost requests are never intercepted by a corporate proxy
        self._session = requests.Session()
        self._session.trust_env = False
        self.timeout_load = 3600  # 1 hour for loading large ETL files
        self.timeout_analyze = 3600  # 1 hour for comprehensive analysis
        
        # Fallback configuration
        self.enable_fallback = enable_fallback
        self.show_console = show_console
        self.speed_exe_path = self._resolve_speed_exe(speed_exe_path)
        
        # Default to same directory as this client file
        if standalone_scripts_dir is None:
            # Use the same directory where this client file is located
            standalone_scripts_dir = Path(__file__).parent
        
        self.standalone_scripts_dir = Path(standalone_scripts_dir)
        
        # Validate paths if fallback enabled
        if self.enable_fallback:
            if not os.path.exists(self.speed_exe_path):
                print(f"[WARNING] SPEED.exe not found at: {self.speed_exe_path}")
                print(f"[WARNING] Fallback mechanism disabled")
                self.enable_fallback = False
            
            if not self.standalone_scripts_dir.exists():
                print(f"[WARNING] Standalone scripts directory not found: {self.standalone_scripts_dir}")
                print(f"[WARNING] Fallback mechanism disabled")
                self.enable_fallback = False


    @staticmethod
    def _resolve_speed_exe(explicit_path: Optional[str] = None) -> str:
        """
        Resolve the speed.exe path using the following priority order:
          1. Explicitly provided path (constructor argument)
          2. SPEED_EXE_PATH environment variable
          3. Common installation directories (64-bit then 32-bit Program Files)
          4. System PATH lookup via shutil.which
          5. Default fallback path (returned even if it doesn't exist, so the
             caller's existence check can emit the appropriate warning)
        """
        candidates = []

        # 1. Explicit argument
        if explicit_path:
            candidates.append(explicit_path)

        # 2. Environment variable
        env_path = os.environ.get("SPEED_EXE_PATH")
        if env_path:
            candidates.append(env_path)

        # 3. Well-known installation directories
        pf64 = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf32 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        for base in [pf64, pf32]:
            candidates.append(os.path.join(base, "SPEED", "speed.exe"))

        # 4. PATH lookup
        which_result = shutil.which("speed")
        if which_result:
            candidates.append(which_result)

        # Return the first path that actually exists
        for path in candidates:
            if path and os.path.exists(path):
                return path

        # 5. Nothing found – return the standard default so the warning is descriptive
        return os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"), "SPEED", "speed.exe"
        )

    def is_service_available(self):
        """Check if the SpeedLibs service is running and healthy"""
        try:
            response = self._session.get(f"{self.base_url}/health", timeout=5)
            health = response.json()
            return health.get("status") == "healthy" and health.get("speedlibs_available", False)
        except Exception:
            return False
    
    def get_service_info(self):
        """Get information about the SpeedLibs service"""
        try:
            response = self._session.get(f"{self.base_url}/info", timeout=5)
            return response.json()
        except Exception as e:
            return {"error": str(e), "service_available": False}
    
    # =========================================================================
    # FALLBACK MECHANISM - Run standalone scripts via speed.exe
    # =========================================================================

    def _run_speed_exe(self, cmd: list, timeout: int) -> tuple:
        """
        Run a speed.exe command and return (returncode, stdout, stderr).

        show_console=True  -> opens a new visible console window on Windows so
                             the user can watch live output.  returncode is read
                             via proc.wait(); stdout/stderr are empty strings
                             because they flow to the window, not to us.
        show_console=False -> runs hidden with output captured (original mode).
        """
        if self.show_console and os.name == 'nt':
            # Windows: write a tiny .bat that runs speed.exe then pauses so the
            # window stays open for the user to read output / errors.
            import tempfile, textwrap
            etl_arg = next((cmd[i + 1] for i, a in enumerate(cmd) if a == '--etl_file'), '')
            bat_lines = textwrap.dedent(f"""\
                @echo off
                title speed.exe - {os.path.basename(etl_arg)}
                {subprocess.list2cmdline(cmd)}
                echo.
                echo [DONE - window will close automatically]
            """)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.bat',
                                             delete=False, encoding='utf-8') as f:
                f.write(bat_lines)
                bat_path = f.name
            try:
                proc = subprocess.Popen(
                    ['cmd.exe', '/C', bat_path],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    raise
                return proc.returncode, '', ''
            finally:
                try:
                    os.unlink(bat_path)
                except OSError:
                    pass
        else:
            # Hidden / non-Windows: capture output silently
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr

    def _run_standalone_comprehensive_analysis(self, etl_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        try:
            # print(f"[FALLBACK] Running standalone comprehensive analysis via speed.exe")
            
            # Locate standalone script
            script_path = self.standalone_scripts_dir / "standalone_comprehensive_analysis.py"
            if not script_path.exists():
                return {
                    "success": False,
                    "error": f"Standalone script not found: {script_path}",
                    "fallback_attempted": True
                }
            
            # Build command
            cmd = [
                self.speed_exe_path,
                "run",
                str(script_path),
                "--etl_file", etl_path
            ]
            
            if output_dir:
                cmd.extend(["--output_dir", output_dir])
            
            # print(f"[FALLBACK] Command: {' '.join(cmd)}")
            
            # Execute via speed.exe
            start_time = time.time()
            returncode, stdout_text, stderr_text = self._run_speed_exe(cmd, self.timeout_analyze)
            elapsed_time = time.time() - start_time

            if returncode != 0:
                return {
                    "success": False,
                    "error": f"Standalone script failed with exit code {returncode}",
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "fallback_attempted": True
                }
            
            # Find generated pickle file
            # Script outputs to ETL directory with timestamped name
            etl_dir = os.path.dirname(os.path.abspath(etl_path))
            etl_basename = os.path.splitext(os.path.basename(etl_path))[0]
            
            # Find most recent pickle file matching pattern
            import glob
            pickle_pattern = os.path.join(etl_dir, f"{etl_basename}_*_dfs.pkl")
            pickle_files = glob.glob(pickle_pattern)
            
            if not pickle_files:
                return {
                    "success": False,
                    "error": f"No pickle file found matching pattern: {pickle_pattern}",
                    "stdout": stdout_text,
                    "fallback_attempted": True
                }
            
            # Get most recent file
            pickle_file = max(pickle_files, key=os.path.getmtime)
            
            # Load pickle and return metadata (matching service response format)
            try:
                with open(pickle_file, 'rb') as f:
                    results_dict = pickle.load(f)

                # Count only DataFrame keys (matches service counting logic)
                df_count = len([k for k, v in results_dict.items() if hasattr(v, 'shape')])

                # ---- Convert pickle → simplified JSON (same as service path) ----
                json_content  = None
                json_file_path = None
                try:
                    import sys as _sys
                    from pathlib import Path as _Path
                    _utilities_path = str(_Path(__file__).parent.parent / "utilities")
                    if _utilities_path not in _sys.path:
                        _sys.path.insert(0, _utilities_path)
                    from pickle_to_json_converter import convert_pickle_to_json
                    conv = convert_pickle_to_json(pickle_file, etl_file_path=etl_path)
                    if conv.get("success"):
                        json_file_path = conv.get("json_file_path")
                        with open(json_file_path, "r", encoding="utf-8") as _f:
                            json_content = json.load(_f)
                except Exception as _je:
                    print(f"[WARNING] JSON conversion failed (non-fatal): {_je}")

                # NORMALISED response — identical keys/types to the service path
                return {
                    "success": True,
                    "processing_time": round(elapsed_time, 2),
                    "pickle_file_path": pickle_file,
                    "pickle_available": True,
                    "dataframe_count": df_count,
                    "dataframe_names": list(results_dict.keys()),
                    "analysis_type": "comprehensive",
                    "file_analyzed": etl_path,
                    "message": "ETL analysis completed",
                    "execution_mode": "standalone_fallback",
                    "fallback_used": True,
                    # JSON summary — agent can summarise immediately without loading the pickle
                    "json_file_path": json_file_path,
                    "json_content":   json_content,
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to load pickle file: {e}",
                    "pickle_file_path": pickle_file,
                    "fallback_attempted": True
                }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Standalone script timed out after {self.timeout_analyze} seconds",
                "fallback_attempted": True
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Fallback execution failed: {str(e)}",
                "fallback_attempted": True
            }
    
    def _run_standalone_teams_analysis(self, etl_path: str, time_range: Optional[tuple] = None,
                                       vcip_time_range: Optional[tuple] = None, 
                                       fps_time_range: Optional[tuple] = None,
                                       constraints_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Run standalone Teams KPI analysis via speed.exe
        
        Args:
            etl_path: Path to ETL file
            time_range: Optional time range tuple
            vcip_time_range: Optional VCIP time range
            fps_time_range: Optional FPS time range
            constraints_file: Optional constraints file
            
        Returns:
            Dictionary with Teams KPI analysis results
        """
        try:
            # print(f"[FALLBACK] Running standalone Teams analysis via speed.exe")
            
            # Locate standalone script
            script_path = self.standalone_scripts_dir / "standalone_teams_analysis.py"
            if not script_path.exists():
                return {
                    "success": False,
                    "error": f"Standalone Teams script not found: {script_path}",
                    "fallback_attempted": True
                }
            
            # Build command
            # Default output_dir to the same directory as the ETL file
            effective_output_dir = os.path.dirname(os.path.abspath(etl_path))
            cmd = [
                self.speed_exe_path,
                "run",
                str(script_path),
                "--etl_file", etl_path,
                "--output_dir", effective_output_dir
            ]

            if time_range:
                cmd.extend(["--time_range", f"{time_range[0]},{time_range[1]}"])
            if vcip_time_range:
                cmd.extend(["--vcip_time_range", f"{vcip_time_range[0]},{vcip_time_range[1]}"])
            if fps_time_range:
                cmd.extend(["--fps_time_range", f"{fps_time_range[0]},{fps_time_range[1]}"])
            if constraints_file:
                cmd.extend(["--constraints_file", constraints_file])

            # print(f"[FALLBACK] Command: {' '.join(cmd)}")
            
            # Execute via speed.exe
            start_time = time.time()
            returncode, stdout_text, stderr_text = self._run_speed_exe(cmd, self.timeout_analyze)
            elapsed_time = time.time() - start_time

            if returncode != 0:
                return {
                    "success": False,
                    "error": f"Standalone Teams script failed with exit code {returncode}",
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "fallback_attempted": True
                }
            
            # Find generated pickle file
            etl_dir = os.path.dirname(os.path.abspath(etl_path))
            etl_basename = os.path.splitext(os.path.basename(etl_path))[0]
            
            import glob
            pickle_pattern = os.path.join(etl_dir, f"{etl_basename}_*_teams_kpi.pkl")
            pickle_files = glob.glob(pickle_pattern)
            
            if not pickle_files:
                return {
                    "success": False,
                    "error": f"No Teams KPI pickle file found matching: {pickle_pattern}",
                    "stdout": stdout_text,
                    "fallback_attempted": True
                }
            
            pickle_file = max(pickle_files, key=os.path.getmtime)
            
            # Load pickle to extract KPI data
            try:
                with open(pickle_file, 'rb') as f:
                    kpi_data = pickle.load(f)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to load Teams KPI pickle: {str(e)}",
                    "pickle_file": pickle_file,
                    "fallback_attempted": True
                }
            
            # print(f"[FALLBACK] [OK] Teams analysis complete: {pickle_file}")
            
            # NORMALISED response — identical keys/types to service path
            return {
                "success": True,
                "processing_time": round(elapsed_time, 2),  # float, same as service
                "analysis_type": "teams_kpi",
                "file_analyzed": etl_path,
                "message": "Teams KPI analysis completed",
                "kpi_data": kpi_data,  # no json_file_path key (never added in standalone)
                "execution_mode": "standalone_fallback",
                "fallback_used": True,
                # Top-level shortcut fields (same as service)
                "media_to_audio_alignment": kpi_data.get("media_to_audio_alignment"),
                "ipu_to_audio_alignment": kpi_data.get("ipu_to_audio_alignment"),
                "wlan_to_audio_alignment": kpi_data.get("wlan_to_audio_alignment"),
                "decode_fps": kpi_data.get("decode_fps"),
                "encode_fps": kpi_data.get("encode_fps"),
                "vpblt_fps": kpi_data.get("vpblt_fps"),
                "camera_fps": kpi_data.get("camera_fps"),
                "constraints_count": kpi_data.get("constraints_count"),
                "constraints_data": kpi_data.get("constraints_data", [])
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Standalone Teams script timed out after {self.timeout_analyze} seconds",
                "fallback_attempted": True
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Fallback Teams execution failed: {str(e)}",
                "fallback_attempted": True
            }
    
    
    
    def load_and_get_comprehensive_analysis(self, etl_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Load ETL file and get comprehensive analysis via the SpeedLibs service
        WITH AUTOMATIC FALLBACK to standalone script if service unavailable
        
        Args:
            etl_path: Path to the ETL file
            output_dir: Optional output directory
            
        Returns:
            Dictionary with analysis results
        """
        # Try service first
        if not self.is_service_available():
            # Service unavailable - try fallback if enabled
            if self.enable_fallback:
                # print(f"[FALLBACK] Service unavailable, attempting standalone execution")
                return self._run_standalone_comprehensive_analysis(etl_path, output_dir)
            else:
                return {
                    "status": "error",
                    "success": False,
                    "message": "SpeedLibs service is not available and fallback is disabled. Please start the service first.",
                    "service_available": False,
                    "fallback_available": False
                }
        
        try:
            payload = {
                "etl_path": etl_path
            }
            if output_dir:
                payload["output_dir"] = output_dir
            
            # Loading and analyzing ETL via service (cannot print in MCP)
            
            response = self._session.post(
                f"{self.base_url}/etl/load_analyze", 
                json=payload, 
                timeout=self.timeout_analyze
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Handle simplified service response format (pickle-only)
                if result.get("status") == "success" and result.get("data"):
                    data = result["data"]

                    # Parse processing_time to float regardless of what service returns
                    raw_pt = data.get("processing_time", 0)
                    try:
                        pt_float = float(str(raw_pt).replace(" seconds", "").replace("s", "").strip())
                    except (ValueError, TypeError):
                        pt_float = 0.0

                    # NORMALISED response — identical keys/types to standalone path
                    return {
                        "success": True,
                        "processing_time": round(pt_float, 2),  # float
                        "pickle_file_path": data.get("pickle_file_path"),
                        "pickle_available": data.get("pickle_available", False),
                        "dataframe_count": data.get("dataframe_count", 0),
                        "analysis_type": data.get("analysis_type", "comprehensive"),
                        "file_analyzed": etl_path,
                        "message": "ETL analysis completed",
                        "execution_mode": "service",
                        "fallback_used": False
                    }
                else:
                    return {
                        "status": "error",
                        "success": False,
                        "message": result.get("message", "Load and analysis failed - no data returned"),
                        "service_response": result
                    }
            else:
                return {
                    "status": "error", 
                    "success": False,
                    "message": f"Service returned status code {response.status_code}: {response.text}",
                    "service_available": True
                }
                
        except requests.exceptions.Timeout:
            return {
                "status": "timeout",
                "success": False,
                "message": f"ETL load and analysis timed out after {self.timeout_analyze} seconds",
                "service_available": True
            }
        except Exception as e:
            # Service error - try fallback if enabled
            if self.enable_fallback:
                # print(f"[FALLBACK] Service error: {str(e)}, attempting standalone execution")
                return self._run_standalone_comprehensive_analysis(etl_path, output_dir)
            else:
                return {
                    "status": "error",
                    "success": False,
                    "message": f"Failed to load and analyze ETL via service: {str(e)}",
                    "service_available": False
                }

    def get_dataframes_dict(self, etl_path: str) -> Dict[str, Any]:
        """
        Get the actual DataFrames from comprehensive analysis
        
        Args:
            etl_path: Path to the ETL file
            
        Returns:
            Dictionary with the full results_dict containing DataFrames
        """
        if not self.is_service_available():
            return {
                "success": False,
                "error": "SpeedLibs service is not available"
            }
        
        try:
            payload = {"etl_path": etl_path}
            
            response = self._session.post(
                f"{self.base_url}/etl/dataframes", 
                json=payload, 
                timeout=self.timeout_analyze
            )
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                return {
                    "success": False,
                    "error": f"Service returned status code {response.status_code}: {response.text}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Exception during dataframes request: {str(e)}"
            }

    def teams_kpi_analysis(self, etl_path: str, time_range: Optional[tuple] = None, 
                          vcip_time_range: Optional[tuple] = None, fps_time_range: Optional[tuple] = None, 
                          constraints_file: Optional[str] = None, operation: str = 'all') -> Dict[str, Any]:
        """
        Perform Teams KPI Analysis using the SpeedLibs service
        WITH AUTOMATIC FALLBACK to standalone script if service unavailable
        
        Args:
            etl_path: Path to the ETL file
            time_range: Optional time range tuple (default: (0, 60))
            vcip_time_range: Optional VCIP time range tuple (default: (2, 10))
            fps_time_range: Optional FPS time range tuple (default: (5, 65))
            constraints_file: Optional path to constraints file
            operation: Which analysis to run - 'all', 'fps', 'vcip', 'constraints' (default: 'all')
            
        Returns:
            Dictionary with Teams KPI analysis results including VCIP alignment, FPS metrics, and constraints
        """
        # Try service first
        if not self.is_service_available():
            # Service unavailable - try fallback if enabled
            if self.enable_fallback:
                # print(f"[FALLBACK] Service unavailable, attempting standalone Teams analysis")
                return self._run_standalone_teams_analysis(etl_path, time_range, vcip_time_range, 
                                                           fps_time_range, constraints_file)
            else:
                return {
                    "success": False,
                    "error": "SpeedLibs service is not available and fallback is disabled",
                    "service_available": False,
                    "fallback_available": False
                }
        
        try:
            payload = {"etl_path": etl_path}
            
            # Add optional parameters if provided
            if time_range is not None:
                payload["time_range"] = time_range
            if vcip_time_range is not None:
                payload["vcip_time_range"] = vcip_time_range
            if fps_time_range is not None:
                payload["fps_time_range"] = fps_time_range
            if constraints_file is not None:
                payload["constraints_file"] = constraints_file
            if operation:
                payload["operation"] = operation
            
            response = self._session.post(
                f"{self.base_url}/etl/teams_kpi_analysis", 
                json=payload, 
                timeout=self.timeout_analyze
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("status") == "success" and result.get("data"):
                    analysis_data = result["data"]

                    # Strip service-internal keys that don't belong in kpi_data
                    kpi_data = {k: v for k, v in analysis_data.items()
                                if k not in ("json_file_path",)}

                    # Parse processing_time to float
                    raw_pt = result.get("processing_time", 0)
                    try:
                        pt_float = float(str(raw_pt).replace(" seconds", "").replace("s", "").strip())
                    except (ValueError, TypeError):
                        pt_float = 0.0

                    # NORMALISED response — identical keys/types to standalone path
                    return {
                        "success": True,
                        "processing_time": round(pt_float, 2),  # float
                        "analysis_type": "teams_kpi",
                        "file_analyzed": etl_path,
                        "message": "Teams KPI analysis completed",
                        "kpi_data": kpi_data,
                        "execution_mode": "service",
                        "fallback_used": False,
                        # Top-level shortcut fields (same as standalone)
                        "media_to_audio_alignment": kpi_data.get("media_to_audio_alignment"),
                        "ipu_to_audio_alignment": kpi_data.get("ipu_to_audio_alignment"),
                        "wlan_to_audio_alignment": kpi_data.get("wlan_to_audio_alignment"),
                        "decode_fps": kpi_data.get("decode_fps"),
                        "encode_fps": kpi_data.get("encode_fps"),
                        "vpblt_fps": kpi_data.get("vpblt_fps"),
                        "camera_fps": kpi_data.get("camera_fps"),
                        "constraints_count": kpi_data.get("constraints_count"),
                        "constraints_data": kpi_data.get("constraints_data", [])
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("message", "Teams KPI analysis failed - no data returned"),
                        "service_response": result
                    }
            else:
                return {
                    "success": False,
                    "error": f"Service returned status code {response.status_code}: {response.text}",
                    "service_available": True
                }
                
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": f"Teams KPI analysis timed out after {self.timeout_analyze} seconds",
                "service_available": True
            }
        except Exception as e:
            # Service error - try fallback if enabled
            if self.enable_fallback:
                # print(f"[FALLBACK] Service error: {str(e)}, attempting standalone Teams analysis")
                return self._run_standalone_teams_analysis(etl_path, time_range, vcip_time_range,
                                                           fps_time_range, constraints_file)
            else:
                return {
                    "success": False,
                    "error": f"Failed to perform Teams KPI analysis via service: {str(e)}",
                    "service_available": False
                }

    def get_trace_summary(self, etl_path: str, time_range: Optional[tuple] = None) -> Dict[str, Any]:
        """
        Get trace summary analysis with platform info and stats via pickle file
        
        Args:
            etl_path: Path to the ETL file
            time_range: Optional tuple of (start, end) time range
            
        Returns:
            Dictionary with:
            - status: "success" or "error"
            - pickle_file_path: Path to pickle file containing DataFrames dict
            - dataframes: Unpickled dictionary of DataFrames (if successful)
            - dataframe_keys: List of available DataFrame keys
        """
        if not self.is_service_available():
            return {
                "status": "error",
                "success": False,
                "message": "SpeedLibs service is not available. Please start the service first.",
                "service_available": False
            }
        
        try:
            payload = {
                "etl_path": etl_path
            }
            if time_range:
                payload["time_range"] = time_range
            
            response = self._session.post(
                f"{self.base_url}/etl/trace_summary", 
                json=payload, 
                timeout=self.timeout_analyze
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("status") == "success" and result.get("data"):
                    data = result["data"]
                    pickle_file_path = data.get("pickle_file_path")
                    
                    # Try to unpickle the DataFrames
                    if pickle_file_path and data.get("pickle_available"):
                        try:
                            import pickle
                            import os
                            
                            if os.path.exists(pickle_file_path):
                                with open(pickle_file_path, 'rb') as f:
                                    dataframes_dict = pickle.load(f)
                                
                                return {
                                    "status": "success",
                                    "success": True,
                                    "pickle_file_path": pickle_file_path,
                                    "dataframes": dataframes_dict,
                                    "dataframe_keys": list(dataframes_dict.keys()),
                                    "dataframe_count": len(dataframes_dict),
                                    "processing_time": data.get("processing_time"),
                                    "message": result.get("message", "Trace summary analysis completed successfully")
                                }
                            else:
                                return {
                                    "status": "error",
                                    "success": False,
                                    "message": f"Pickle file not found: {pickle_file_path}",
                                    "pickle_file_path": pickle_file_path
                                }
                        except Exception as pickle_error:
                            return {
                                "status": "error",
                                "success": False,
                                "message": f"Failed to unpickle DataFrames: {str(pickle_error)}",
                                "pickle_file_path": pickle_file_path
                            }
                    else:
                        return {
                            "status": "error",
                            "success": False,
                            "message": "Pickle file not available in service response",
                            "service_response": data
                        }
                else:
                    return {
                        "status": "error",
                        "success": False,
                        "message": result.get("message", "Trace summary failed - no data returned"),
                        "service_response": result
                    }
            else:
                return {
                    "status": "error", 
                    "success": False,
                    "message": f"Service returned status code {response.status_code}: {response.text}",
                    "service_available": True
                }
                
        except requests.exceptions.Timeout:
            return {
                "status": "timeout",
                "success": False,
                "message": f"Trace summary timed out after {self.timeout_analyze} seconds",
                "service_available": True
            }
        except Exception as e:
            return {
                "status": "error",
                "success": False,
                "message": f"Failed to get trace summary via service: {str(e)}",
                "service_available": False
            }
    
    def analyze_constraints(self, etl_path: str, constraints_file: str, socwatch_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze constraints on an ETL trace
        
        Args:
            etl_path: Path to the ETL file
            constraints_file: Path to the constraints definition file
            socwatch_file: Optional path to socwatch file for power analysis
            
        Returns:
            Dictionary with:
            - success: True if analysis succeeded
            - pickle_file_path: Path to pickle file containing results DataFrame
            - result_shape: Shape of the results DataFrame
            - processing_time: Time taken for analysis
        """
        if not self.is_service_available():
            return {
                "status": "error",
                "success": False,
                "message": "SpeedLibs service is not available. Please start the service first.",
                "service_available": False
            }
        
        try:
            payload = {
                "etl_path": etl_path,
                "constraints_file": constraints_file
            }
            if socwatch_file:
                payload["socwatch_file"] = socwatch_file
            
            response = self._session.post(
                f"{self.base_url}/etl/analyze_constraints", 
                json=payload, 
                timeout=self.timeout_analyze
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("status") == "success" and result.get("data"):
                    data = result["data"]
                    return {
                        "success": True,
                        "pickle_file_path": data.get("pickle_file_path"),
                        "pickle_available": data.get("pickle_available", False),
                        "result_shape": data.get("result_shape"),
                        "constraints_file": data.get("constraints_file"),
                        "socwatch_file": data.get("socwatch_file"),
                        "processing_time": data.get("processing_time"),
                        "message": result.get("message", "Constraints analysis completed successfully")
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("message", "Constraints analysis failed"),
                        "service_response": result
                    }
            else:
                return {
                    "success": False,
                    "error": f"Service returned status code {response.status_code}: {response.text}"
                }
                
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": f"Constraints analysis timed out after {self.timeout_analyze} seconds"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to analyze constraints via service: {str(e)}"
            }

# Global client instance — standalone-only, no REST service required
_standalone_client = SpeedLibsServiceClient(enable_fallback=True)


def load_and_get_comprehensive_analysis(etl_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Load ETL and get comprehensive analysis via standalone speed.exe script.
    Returns pickle_file_path (for follow-up queries) AND json_content (for immediate summarisation).
    No REST service required.
    """
    return _standalone_client._run_standalone_comprehensive_analysis(etl_path, output_dir)


def teams_kpi_analysis(etl_path: str, time_range: Optional[tuple] = None,
                       vcip_time_range: Optional[tuple] = None, fps_time_range: Optional[tuple] = None,
                       constraints_file: Optional[str] = None, operation: str = 'all') -> Dict[str, Any]:
    """
    Perform Teams KPI analysis via standalone speed.exe script.
    No REST service required.

    Args:
        operation: 'all', 'fps', 'vcip', 'pipeline', or 'constraints'
    """
    return _standalone_client._run_standalone_teams_analysis(
        etl_path, time_range, vcip_time_range, fps_time_range, constraints_file
    )


def get_trace_summary(etl_path: str, time_range: Optional[tuple] = None) -> Dict[str, Any]:
    """Trace summary — not available as standalone script yet."""
    return {
        "success": False,
        "error": "get_trace_summary is not available in standalone mode. Use load_and_get_comprehensive_analysis instead."
    }


def analyze_constraints(etl_path: str, constraints_file: str, socwatch_file: Optional[str] = None) -> Dict[str, Any]:
    """Constraints analysis — not available as standalone script yet."""
    return {
        "success": False,
        "error": "analyze_constraints is not available in standalone mode. Constraints are included in load_and_get_comprehensive_analysis."
    }


def check_service_status() -> Dict[str, Any]:
    """Service status — always returns standalone mode info (REST service not used)."""
    return {
        "status": "standalone",
        "message": "Running in standalone mode — speed.exe scripts called directly, no REST service required.",
        "speed_exe_path": _standalone_client.speed_exe_path,
        "speed_exe_found": os.path.exists(_standalone_client.speed_exe_path),
    }
