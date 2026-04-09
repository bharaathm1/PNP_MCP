"""
PnP Tools - Plug and Play orchestration and power file detection for AutoBots agent

This module provides comprehensive file detection and analysis tools for:
- Power measurement files (PACS and FlexLogger formats)
- SocWatch CSV output files
- ETL trace files for Windows Event Tracing
- General file discovery
- DataFrame loading and analysis
- Context inventory management
"""

from app import mcp
from typing import Annotated, Dict, Any, List, Optional
from pydantic import Field
import os
import sys
import pickle
import tempfile
import pandas as pd
import glob
import json
from datetime import datetime

# Get the workspace root dynamically
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_CURRENT_DIR))))
_AGENTS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_CURRENT_DIR)))
CRT_WORKING_PATH = os.path.join(_WORKSPACE_ROOT, "crt")
SDK_WORKING_PATH = os.path.join(_WORKSPACE_ROOT, "applications.services.design-system.autobots.autobots-sdk_new_version")
PNP_AGENTS_PATH = os.path.join(_WORKSPACE_ROOT, "PnP_agents")

# Set environment variables
os.environ["AUTOBOTS_SDK_TOOL_PATH"] = SDK_WORKING_PATH
os.environ["AUTOBOTS_CONFIG_PATH"] = CRT_WORKING_PATH

# Add paths
sys.path.insert(0, SDK_WORKING_PATH)
sys.path.insert(0, _AGENTS_ROOT)
sys.path.insert(0, PNP_AGENTS_PATH)

# Storage for loaded DataFrames
DATAFRAMES_STORAGE = {}

# Context inventory
CONTEXT_INVENTORY = {
    "power_analysis": {},
    "socwatch_analysis": {},
    "config_analysis": {},
    "etl_analysis": {},
    "summary_tables_created": []
}


# ===== HELPER FUNCTIONS =====

def _is_socwatch_file(csv_path: str) -> bool:
    """Detect if a CSV file is a SocWatch output file."""
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            first_lines = [f.readline() for _ in range(50)]
        
        content = ''.join(first_lines)
        socwatch_markers = [
            "Intel(R) SoC Watch",
            "SoC Watch for Windows",
            "Package C-State Summary",
            "Core C-State Summary",
            "CPU P-State/Frequency Summary"
        ]
        marker_count = sum(1 for marker in socwatch_markers if marker in content)
        return marker_count >= 2
    except Exception:
        return False


def _detect_file_type_from_content(csv_path: str) -> str:
    """Detect power measurement file type by analyzing CSV header."""
    try:
        df_header = pd.read_csv(csv_path, nrows=0)
        columns = [str(col).strip() for col in df_header.columns]
        
        if "Property Name" in columns or (len(columns) > 0 and "Property" in columns[0]):
            return "flexlogger_summary"
        
        if "Name" in columns and "Peak" in columns and "Average" in columns:
            return "summary"
        
        if "Signal Name" in columns and any(col in columns for col in ["Math", "DAQ", "Channel", "Range"]):
            return "config"
        
        if "Time" in columns:
            power_cols = [col for col in columns if col.startswith("P_")]
            if power_cols:
                return "math_trace"
        
        if "Time" in columns:
            v_cols = [col for col in columns if col.startswith("V_")]
            i_cols = [col for col in columns if col.startswith("I_")]
            if v_cols and i_cols:
                return "channel_trace"
        
        return "unknown"
    except Exception:
        return "unknown"


def detect_power_format(folder_path: str) -> Dict[str, Any]:
    """Detect power measurement format: PACS or FlexLogger."""
    try:
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            return {
                "format": "unknown",
                "detected_files": {},
                "confidence": 0.0,
                "reason": "Invalid folder path"
            }
        
        all_files = os.listdir(folder_path)
        all_paths = [os.path.join(folder_path, f) for f in all_files]
        
        # FlexLogger detection
        xml_config = [f for f in all_paths if f.endswith('.xml') and 'nidaq' in os.path.basename(f).lower()]
        flexlogger_summary = [f for f in all_paths if '_Raw_Summary.csv' in os.path.basename(f)]
        flexlogger_raw = [f for f in all_paths if '_Raw.csv' in os.path.basename(f) and '_Summary' not in os.path.basename(f)]
        
        if xml_config and flexlogger_summary:
            return {
                "format": "FlexLogger",
                "detected_files": {
                    "config": xml_config[0],
                    "summary": flexlogger_summary[0],
                    "raw_traces": flexlogger_raw
                },
                "confidence": 0.95,
                "reason": "Found XML config and _Raw_Summary.csv files"
            }
        
        # PACS detection
        config_csv = [f for f in all_paths if 'config-details.csv' in os.path.basename(f).lower()]
        channel_csv = [f for f in all_paths if 'channel-traces.csv' in os.path.basename(f).lower()]
        math_csv = [f for f in all_paths if 'math-traces.csv' in os.path.basename(f).lower()]
        summary_csv = [f for f in all_paths if 'summary.csv' in os.path.basename(f).lower() and 'raw' not in os.path.basename(f).lower()]
        
        if config_csv and summary_csv:
            return {
                "format": "PACS",
                "detected_files": {
                    "config": config_csv[0],
                    "summary": summary_csv[0],
                    "raw_traces": channel_csv,
                    "calculated_traces": math_csv[0] if math_csv else None
                },
                "confidence": 0.95,
                "reason": "Found config-details.csv and summary.csv files"
            }
        
        return {
            "format": "unknown",
            "detected_files": {},
            "confidence": 0.0,
            "reason": "No recognizable power measurement files found"
        }
    except Exception as e:
        return {
            "format": "unknown",
            "detected_files": {},
            "confidence": 0.0,
            "reason": f"Error during detection: {str(e)}"
        }


# ===== MCP TOOLS =====

@mcp.tool(
    description="Identify power measurement files in a folder with format detection (PACS or FlexLogger)",
    tags={"power", "detection", "files"}
)
def identify_power_files(
    folder_path: Annotated[str, Field(
        description="Path to folder containing power measurement files"
    )],
    recursive: Annotated[bool, Field(
        description="If True, recursively search subdirectories",
        default=True
    )] = True
) -> dict:
    """
    Scan folder and identify power measurement files with format detection.
    
    Detects PACS format (config-details.csv, summary.csv, channel-traces.csv, math-traces.csv)
    or FlexLogger format (XML config, *_Raw_Summary.csv, *_Raw.csv).
    
    Returns format type, detected files, and metadata for delegation to power_agent.
    """
    try:
        if not os.path.exists(folder_path):
            return {
                "success": False,
                "error": f"Folder does not exist: {folder_path}"
            }
        
        if not os.path.isdir(folder_path):
            return {
                "success": False,
                "error": f"Path is not a directory: {folder_path}"
            }
        
        # Detect format
        format_info = detect_power_format(folder_path)
        detected_format = format_info["format"]
        
        if detected_format == "unknown":
            return {
                "success": False,
                "format": "unknown",
                "message": "No power measurement files detected in folder",
                "folder_path": folder_path
            }
        
        # Find CSV files
        csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
        xml_files = glob.glob(os.path.join(folder_path, "*.xml"))
        
        # Build response
        detected_files = format_info.get("detected_files", {})
        
        return {
            "success": True,
            "format": detected_format,
            "format_confidence": format_info["confidence"],
            "format_detection_reason": format_info["reason"],
            "folder_path": folder_path,
            "total_csv_files": len(csv_files),
            "detected_files": detected_files,
            "message": f"Detected {detected_format} format with {len(csv_files)} CSV files",
            "next_steps": [
                f"Delegate to power_agent with format={detected_format}",
                "Power agent will parse and analyze the files"
            ]
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to identify power files: {str(e)}"
        }


@mcp.tool(
    description="Identify Intel SocWatch CSV output files in a folder",
    tags={"socwatch", "detection", "files"}
)
def identify_socwatch_files(
    folder_path: Annotated[str, Field(
        description="Path to folder containing potential SocWatch files"
    )]
) -> dict:
    """
    Scan folder and identify Intel SocWatch CSV output files.
    
    Detects SocWatch files by analyzing content for characteristic markers like
    "Intel(R) SoC Watch", "Package C-State Summary", etc.
    
    Returns list of detected SocWatch files for delegation to socwatch_agent.
    """
    try:
        if not os.path.exists(folder_path):
            return {
                "success": False,
                "error": f"Folder does not exist: {folder_path}"
            }
        
        # Find all CSV files
        csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
        
        if not csv_files:
            return {
                "success": False,
                "message": "No CSV files found in folder",
                "folder_path": folder_path
            }
        
        # Identify SocWatch files
        socwatch_files = []
        for csv_path in csv_files:
            if _is_socwatch_file(csv_path):
                socwatch_files.append({
                    "file_path": csv_path,
                    "file_name": os.path.basename(csv_path),
                    "file_size_mb": round(os.path.getsize(csv_path) / (1024 * 1024), 2)
                })
        
        if not socwatch_files:
            return {
                "success": False,
                "message": "No SocWatch files detected",
                "folder_path": folder_path,
                "csv_files_scanned": len(csv_files)
            }
        
        # Update context inventory
        CONTEXT_INVENTORY["socwatch_analysis"][folder_path] = {
            "files": [f["file_name"] for f in socwatch_files],
            "analyzed": False,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return {
            "success": True,
            "socwatch_files": socwatch_files,
            "file_count": len(socwatch_files),
            "folder_path": folder_path,
            "message": f"Found {len(socwatch_files)} SocWatch files",
            "next_steps": [
                "Delegate to socwatch_agent for analysis",
                "Agent will parse and extract C-state, P-state, and power metrics"
            ]
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to identify SocWatch files: {str(e)}"
        }


@mcp.tool(
    description="Identify ETL (Event Trace Log) files for Windows Event Tracing analysis",
    tags={"etl", "detection", "files", "windows"}
)
def identify_etl_files(
    folder_path: Annotated[str, Field(
        description="Path to folder containing potential ETL files"
    )],
    recursive: Annotated[bool, Field(
        description="If True, search subdirectories",
        default=True
    )] = True
) -> dict:
    """
    Scan folder and identify ETL (.etl) trace files for Windows Event Tracing.
    
    ETL files are binary Windows Event Tracing files that require specialized parsing.
    Returns list of detected ETL files for delegation to etl_analyzer_agent_windows.
    """
    try:
        if not os.path.exists(folder_path):
            return {
                "success": False,
                "error": f"Folder does not exist: {folder_path}"
            }
        
        # Find ETL files
        if recursive:
            etl_files = []
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith('.etl'):
                        etl_files.append(os.path.join(root, file))
        else:
            etl_files = glob.glob(os.path.join(folder_path, "*.etl"))
        
        if not etl_files:
            return {
                "success": False,
                "message": "No ETL files found",
                "folder_path": folder_path
            }
        
        # Build file metadata
        etl_file_info = []
        for etl_path in etl_files:
            etl_file_info.append({
                "file_path": etl_path,
                "file_name": os.path.basename(etl_path),
                "file_size_mb": round(os.path.getsize(etl_path) / (1024 * 1024), 2),
                "modified_time": datetime.fromtimestamp(os.path.getmtime(etl_path)).strftime("%Y-%m-%d %H:%M:%S")
            })
        
        return {
            "success": True,
            "etl_files": etl_file_info,
            "file_count": len(etl_file_info),
            "folder_path": folder_path,
            "message": f"Found {len(etl_file_info)} ETL files",
            "next_steps": [
                "Delegate to etl_analyzer_agent_windows for parsing",
                "Agent will extract trace events and generate DataFrames"
            ]
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to identify ETL files: {str(e)}"
        }


@mcp.tool(
    description="General-purpose file discovery to find files by extension",
    tags={"files", "discovery", "search"}
)
def discover_files(
    folder_path: Annotated[str, Field(
        description="Path to folder to search"
    )],
    file_extensions: Annotated[Optional[List[str]], Field(
        description="List of extensions to search for (e.g., ['.csv', '.md', '.json']). If None, searches common types",
        default=None
    )] = None,
    recursive: Annotated[bool, Field(
        description="If True, search subdirectories (max depth: 3)",
        default=True
    )] = True
) -> dict:
    """
    Find files by extension in a folder structure.
    
    Provides flexible file discovery for any file types (CSV, MD, JSON, TXT, etc.)
    without parsing or classifying them. Simply lists matching files.
    
    Default extensions if none specified: .csv, .md, .json, .txt, .xlsx
    """
    try:
        if not os.path.exists(folder_path):
            return {
                "success": False,
                "error": f"Folder does not exist: {folder_path}"
            }
        
        # Default extensions
        if file_extensions is None:
            file_extensions = ['.csv', '.md', '.json', '.txt', '.xlsx']
        
        # Normalize extensions
        file_extensions = [ext.lower() if ext.startswith('.') else f'.{ext.lower()}' for ext in file_extensions]
        
        # Find files
        files_by_type = {ext: [] for ext in file_extensions}
        
        if recursive:
            for root, dirs, files in os.walk(folder_path):
                # Limit depth
                depth = root[len(folder_path):].count(os.sep)
                if depth > 3:
                    continue
                
                for file in files:
                    file_lower = file.lower()
                    for ext in file_extensions:
                        if file_lower.endswith(ext):
                            full_path = os.path.join(root, file)
                            files_by_type[ext].append({
                                "file_path": full_path,
                                "file_name": file,
                                "relative_path": os.path.relpath(full_path, folder_path),
                                "size_kb": round(os.path.getsize(full_path) / 1024, 2)
                            })
        else:
            for file in os.listdir(folder_path):
                file_path = os.path.join(folder_path, file)
                if os.path.isfile(file_path):
                    file_lower = file.lower()
                    for ext in file_extensions:
                        if file_lower.endswith(ext):
                            files_by_type[ext].append({
                                "file_path": file_path,
                                "file_name": file,
                                "size_kb": round(os.path.getsize(file_path) / 1024, 2)
                            })
        
        # Count total files
        total_files = sum(len(files) for files in files_by_type.values())
        
        # Remove empty types
        files_by_type = {ext: files for ext, files in files_by_type.items() if files}
        
        return {
            "success": True,
            "folder_path": folder_path,
            "files_by_type": files_by_type,
            "total_files": total_files,
            "extensions_searched": file_extensions,
            "message": f"Found {total_files} files across {len(files_by_type)} file types"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to discover files: {str(e)}"
        }


@mcp.tool(
    description="Load a CSV file into memory for analysis",
    tags={"data", "csv", "loading"}
)
def load_csv(
    file_path: Annotated[str, Field(
        description="Path to CSV file"
    )],
    dataframe_name: Annotated[str, Field(
        description="Name to assign to the loaded DataFrame",
        default="df"
    )] = "df"
) -> dict:
    """Load a CSV file into memory and store it for later analysis."""
    try:
        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": f"File not found: {file_path}"
            }
        
        # Load CSV
        df = pd.read_csv(file_path)
        
        # Create pickle
        scratch_dir = os.environ.get("MCP_AGENT_SCRATCH_DIR", tempfile.gettempdir())
        pickle_name = f"{dataframe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
        pickle_path = os.path.join(scratch_dir, pickle_name)
        
        with open(pickle_path, 'wb') as f:
            pickle.dump(df, f)
        
        # Store reference
        DATAFRAMES_STORAGE[dataframe_name] = pickle_path
        
        return {
            "success": True,
            "dataframe_name": dataframe_name,
            "pickle_path": pickle_path,
            "shape": {"rows": len(df), "columns": len(df.columns)},
            "columns": list(df.columns),
            "memory_mb": round(df.memory_usage(deep=True).sum() / (1024 * 1024), 2),
            "message": f"Loaded CSV with {len(df)} rows and {len(df.columns)} columns"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load CSV: {str(e)}"
        }


@mcp.tool(
    description="Load a JSON file into memory for analysis",
    tags={"data", "json", "loading"}
)
def load_json(
    file_path: Annotated[str, Field(
        description="Path to JSON file"
    )],
    dataframe_name: Annotated[str, Field(
        description="Name to assign to the loaded DataFrame",
        default="df"
    )] = "df"
) -> dict:
    """Load a JSON file into memory and convert to DataFrame if possible."""
    try:
        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": f"File not found: {file_path}"
            }
        
        # Load JSON
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Try to convert to DataFrame
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            df = pd.DataFrame([data])
        else:
            return {
                "success": False,
                "error": "JSON data cannot be converted to DataFrame"
            }
        
        # Create pickle
        scratch_dir = os.environ.get("MCP_AGENT_SCRATCH_DIR", tempfile.gettempdir())
        pickle_name = f"{dataframe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
        pickle_path = os.path.join(scratch_dir, pickle_name)
        
        with open(pickle_path, 'wb') as f:
            pickle.dump(df, f)
        
        DATAFRAMES_STORAGE[dataframe_name] = pickle_path
        
        return {
            "success": True,
            "dataframe_name": dataframe_name,
            "pickle_path": pickle_path,
            "shape": {"rows": len(df), "columns": len(df.columns)},
            "columns": list(df.columns),
            "message": f"Loaded JSON with {len(df)} rows and {len(df.columns)} columns"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load JSON: {str(e)}"
        }


@mcp.tool(
    description="Read and parse a markdown (.md) file",
    tags={"markdown", "documentation", "reading"}
)
def read_markdown_file(
    file_path: Annotated[str, Field(
        description="Path to the markdown file (must end with .md)"
    )]
) -> dict:
    """
    Read markdown file and return content with metadata.
    
    Useful for reading documentation, instructions, configuration notes,
    or any markdown-formatted text files.
    """
    try:
        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": f"File not found: {file_path}"
            }
        
        if not file_path.lower().endswith('.md'):
            return {
                "success": False,
                "error": "File must have .md extension"
            }
        
        # Read file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract metadata
        lines = content.split('\n')
        headers = [line for line in lines if line.strip().startswith('#')]
        
        return {
            "success": True,
            "file_path": file_path,
            "content": content,
            "size_bytes": len(content.encode('utf-8')),
            "line_count": len(lines),
            "char_count": len(content),
            "preview": content[:500],
            "headers": headers[:20],  # First 20 headers
            "message": f"Read markdown file with {len(lines)} lines"
        }
    except UnicodeDecodeError as e:
        return {
            "success": False,
            "error": f"Failed to decode file (encoding issue): {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to read markdown file: {str(e)}"
        }


@mcp.tool(
    description="Analyze a loaded DataFrame using natural language queries",
    tags={"analysis", "dataframe", "query"}
)
def analyze_dataframe(
    dataframe_name: Annotated[str, Field(
        description="Name of the DataFrame to analyze"
    )],
    query: Annotated[str, Field(
        description="Natural language query about the DataFrame"
    )]
) -> dict:
    """
    Analyze a loaded DataFrame using natural language queries.
    Uses LLM to generate and execute pandas code.
    """
    if dataframe_name not in DATAFRAMES_STORAGE:
        return {
            "success": False,
            "error": f"DataFrame '{dataframe_name}' not found. Load it first using load_csv or load_json.",
            "available_dataframes": list(DATAFRAMES_STORAGE.keys())
        }
    
    try:
        # Load DataFrame from pickle
        pickle_path = DATAFRAMES_STORAGE[dataframe_name]
        with open(pickle_path, 'rb') as f:
            df = pickle.load(f)
        
        # Analyze using shared utility (assuming it exists)
        from _shared_utilities.dataframe_analysis import analyze_dataframe_with_llm
        result = analyze_dataframe_with_llm(df, query)
        
        return {
            "success": True,
            "dataframe_name": dataframe_name,
            "query": query,
            "result": result
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to analyze DataFrame: {str(e)}"
        }


@mcp.tool(
    description="Get comprehensive inventory of all data currently available in context",
    tags={"context", "inventory", "status"}
)
def get_context_inventory() -> dict:
    """
    Get inventory of all analyzed data in context.
    
    **USE THIS BEFORE CALLING SUB-AGENTS!**
    
    Shows:
    - What folders have been analyzed for power/socwatch/config/ETL files
    - What use cases and files have been processed
    - What summary tables have been created
    - What data is available for direct comparison
    
    Decision Making:
    - If inventory shows data is available → Use it directly
    - If inventory shows data is missing → Call appropriate sub-agent
    """
    try:
        # Count available data
        power_folders = len(CONTEXT_INVENTORY["power_analysis"])
        socwatch_folders = len(CONTEXT_INVENTORY["socwatch_analysis"])
        config_folders = len(CONTEXT_INVENTORY["config_analysis"])
        etl_files = len(CONTEXT_INVENTORY["etl_analysis"])
        summary_tables = len(CONTEXT_INVENTORY["summary_tables_created"])
        dataframes = len(DATAFRAMES_STORAGE)
        
        # Check if comparison is possible
        can_compare = power_folders >= 2 or socwatch_folders >= 2
        
        return {
            "success": True,
            "summary": {
                "power_analysis_folders": power_folders,
                "socwatch_analysis_folders": socwatch_folders,
                "config_analysis_folders": config_folders,
                "etl_files_analyzed": etl_files,
                "summary_tables_created": summary_tables,
                "loaded_dataframes": dataframes,
                "can_compare": can_compare
            },
            "power_analysis": CONTEXT_INVENTORY["power_analysis"],
            "socwatch_analysis": CONTEXT_INVENTORY["socwatch_analysis"],
            "config_analysis": CONTEXT_INVENTORY["config_analysis"],
            "etl_analysis": CONTEXT_INVENTORY["etl_analysis"],
            "summary_tables": CONTEXT_INVENTORY["summary_tables_created"],
            "available_dataframes": list(DATAFRAMES_STORAGE.keys()),
            "message": f"Context contains {power_folders} power analyses, {socwatch_folders} SocWatch analyses, {dataframes} DataFrames"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to get context inventory: {str(e)}"
        }


@mcp.tool(
    description="Check if an ETL file has already been analyzed and is in context",
    tags={"etl", "context", "check"}
)
def check_etl_in_context(
    etl_file_path: Annotated[str, Field(
        description="Full path to the ETL file to check"
    )],
    analysis_type: Annotated[Optional[str], Field(
        description="Type of analysis: 'trace_summary', 'comprehensive', or 'teams'",
        default=None
    )] = None,
    time_range: Annotated[Optional[str], Field(
        description="Time range string like '(0, 60)', '(30, 90)', or 'full'",
        default=None
    )] = None
) -> dict:
    """
    Check if ETL file analysis is already available in context.
    
    Helps avoid re-parsing ETL files by checking if they've been analyzed already.
    """
    etl_filename = os.path.basename(etl_file_path)
    
    if etl_filename not in CONTEXT_INVENTORY["etl_analysis"]:
        return {
            "in_context": False,
            "etl_file": etl_filename,
            "message": "ETL file has not been analyzed yet"
        }
    
    etl_data = CONTEXT_INVENTORY["etl_analysis"][etl_filename]
    
    # Check specific analysis type and time range
    if analysis_type and time_range:
        if analysis_type in etl_data and time_range in etl_data[analysis_type]:
            analysis_info = etl_data[analysis_type][time_range]
            return {
                "in_context": True,
                "etl_file": etl_filename,
                "analysis_type": analysis_type,
                "time_range": time_range,
                "pickle_path": analysis_info["pickle_path"],
                "dataframe_keys": analysis_info["dataframe_keys"],
                "analyzed_at": analysis_info["analyzed_at"],
                "message": "ETL analysis is available in context"
            }
        else:
            return {
                "in_context": False,
                "etl_file": etl_filename,
                "message": f"ETL file analyzed but not for {analysis_type}/{time_range}"
            }
    
    # Return all available analyses
    return {
        "in_context": True,
        "etl_file": etl_filename,
        "available_analyses": etl_data,
        "message": f"ETL file has {len(etl_data)} analysis types available"
    }


@mcp.tool(
    description="Track ETL file analysis to avoid re-parsing",
    tags={"etl", "tracking", "context"}
)
def track_etl_analysis(
    etl_file_path: Annotated[str, Field(
        description="Full path to the ETL file that was analyzed"
    )],
    analysis_type: Annotated[str, Field(
        description="Type of analysis performed: 'trace_summary', 'comprehensive', or 'teams'"
    )],
    time_range: Annotated[str, Field(
        description="Time range analyzed, e.g., '(0, 60)', '(30, 90)', or 'full'",
        default="full"
    )] = "full",
    pickle_path: Annotated[Optional[str], Field(
        description="Path to the pickle file containing DataFrames",
        default=None
    )] = None,
    dataframe_keys: Annotated[Optional[List[str]], Field(
        description="List of DataFrame names available in the pickle",
        default=None
    )] = None
) -> dict:
    """
    Track ETL analysis to inventory for future reference.
    
    Call this after delegating to etl_analyzer_agent_windows to register
    the analysis results in context.
    """
    etl_filename = os.path.basename(etl_file_path)
    
    # Initialize structure if needed
    if etl_filename not in CONTEXT_INVENTORY["etl_analysis"]:
        CONTEXT_INVENTORY["etl_analysis"][etl_filename] = {}
    
    if analysis_type not in CONTEXT_INVENTORY["etl_analysis"][etl_filename]:
        CONTEXT_INVENTORY["etl_analysis"][etl_filename][analysis_type] = {}
    
    # Store analysis info
    CONTEXT_INVENTORY["etl_analysis"][etl_filename][analysis_type][time_range] = {
        "pickle_path": pickle_path,
        "dataframe_keys": dataframe_keys or [],
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "etl_full_path": etl_file_path
    }
    
    return {
        "success": True,
        "etl_file": etl_filename,
        "analysis_type": analysis_type,
        "time_range": time_range,
        "message": f"Tracked ETL analysis: {etl_filename} ({analysis_type}, {time_range})"
    }


@mcp.tool(
    description="Register parsed data from sub-agents into context",
    tags={"context", "registration", "data"}
)
def register_parsed_data(
    parsed_files: Annotated[Dict[str, Any], Field(
        description="Dictionary of parsed files with their pickle paths and metadata"
    )],
    source_agent: Annotated[str, Field(
        description="Name of the agent that performed the parsing",
        default="sub_agent"
    )] = "sub_agent"
) -> dict:
    """
    Register parsed data from sub-agents into context inventory.
    
    Allows tracking of what data has been parsed and is available
    for analysis without re-parsing.
    """
    try:
        registered_count = 0
        
        for key, file_info in parsed_files.items():
            if "pickle_path" in file_info:
                DATAFRAMES_STORAGE[key] = file_info["pickle_path"]
                registered_count += 1
        
        return {
            "success": True,
            "source_agent": source_agent,
            "registered_count": registered_count,
            "registered_keys": list(parsed_files.keys()),
            "message": f"Registered {registered_count} data items from {source_agent}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to register parsed data: {str(e)}"
        }


@mcp.tool(
    description="Load dashboard pickle file containing multiple DataFrames",
    tags={"data", "pickle", "dashboard"}
)
def load_dashboard_pickle(
    pickle_path: Annotated[str, Field(
        description="Path to the dashboard pickle file"
    )]
) -> dict:
    """
    Load a dashboard pickle file that contains multiple DataFrames.
    
    Dashboard pickles typically contain summary data organized by
    different analysis dimensions.
    """
    try:
        if not os.path.exists(pickle_path):
            return {
                "success": False,
                "error": f"Pickle file not found: {pickle_path}"
            }
        
        # Load pickle
        with open(pickle_path, 'rb') as f:
            data = pickle.load(f)
        
        if not isinstance(data, dict):
            return {
                "success": False,
                "error": "Pickle file does not contain a dictionary of DataFrames"
            }
        
        # Register each DataFrame
        for key, df in data.items():
            if isinstance(df, pd.DataFrame):
                DATAFRAMES_STORAGE[key] = pickle_path
        
        return {
            "success": True,
            "pickle_path": pickle_path,
            "dataframe_keys": list(data.keys()),
            "dataframe_count": len(data),
            "message": f"Loaded dashboard pickle with {len(data)} DataFrames"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load dashboard pickle: {str(e)}"
        }


@mcp.tool(
    description="Load ETL pickle file containing trace analysis DataFrames",
    tags={"etl", "pickle", "data"}
)
def load_etl_pickle(
    pickle_path: Annotated[str, Field(
        description="Path to the ETL pickle file"
    )],
    etl_file_name: Annotated[Optional[str], Field(
        description="Original ETL file name for context tracking",
        default=None
    )] = None
) -> dict:
    """
    Load an ETL pickle file containing trace analysis DataFrames.
    
    ETL pickles contain parsed event trace data from Windows Event Tracing.
    """
    try:
        if not os.path.exists(pickle_path):
            return {
                "success": False,
                "error": f"Pickle file not found: {pickle_path}"
            }
        
        # Load pickle
        with open(pickle_path, 'rb') as f:
            data = pickle.load(f)
        
        if not isinstance(data, dict):
            return {
                "success": False,
                "error": "Pickle file does not contain a dictionary"
            }
        
        # Register DataFrames
        dataframe_keys = []
        for key, value in data.items():
            if isinstance(value, pd.DataFrame):
                DATAFRAMES_STORAGE[key] = pickle_path
                dataframe_keys.append(key)
        
        return {
            "success": True,
            "pickle_path": pickle_path,
            "etl_file_name": etl_file_name,
            "dataframe_keys": dataframe_keys,
            "dataframe_count": len(dataframe_keys),
            "message": f"Loaded ETL pickle with {len(dataframe_keys)} DataFrames"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load ETL pickle: {str(e)}"
        }


@mcp.tool(
    description="Load power rail knowledge base for interpreting power measurements",
    tags={"power", "knowledge", "rails"}
)
def load_power_rail_knowledge() -> dict:
    """
    Load power rail knowledge base containing SoC and platform rail definitions.
    
    Provides information about power rails, their connections to SoCwatch metrics,
    and platform-specific power domains.
    """
    try:
        # Look for knowledge base JSON file
        kb_json_path = os.path.join(_AGENTS_ROOT, "knowledge_base", "power_rails.json")
        
        if not os.path.exists(kb_json_path):
            return {
                "success": False,
                "error": f"Knowledge base not found: {kb_json_path}",
                "message": "Power rail knowledge base file does not exist"
            }
        
        # Load JSON
        with open(kb_json_path, 'r', encoding='utf-8') as f:
            kb = json.load(f)
        
        # Extract rails
        all_rails = kb['power_rails']['soc_rails'] + kb['power_rails']['platform_rails']
        
        # Build connection map
        connection_map = {
            "rail_to_metrics": {},
            "metric_to_rails": {}
        }
        
        for rail in all_rails:
            rail_name = rail['name']
            metrics = rail.get('socwatch_metrics', [])
            connection_map["rail_to_metrics"][rail_name] = metrics
            
            for metric in metrics:
                metric_key = metric.strip()
                if metric_key not in connection_map["metric_to_rails"]:
                    connection_map["metric_to_rails"][metric_key] = []
                connection_map["metric_to_rails"][metric_key].append(rail_name)
        
        return {
            "success": True,
            "metadata": kb['metadata'],
            "soc_rails": kb['power_rails']['soc_rails'],
            "platform_rails": kb['power_rails']['platform_rails'],
            "rail_count": {
                "soc": len(kb['power_rails']['soc_rails']),
                "platform": len(kb['power_rails']['platform_rails']),
                "total": len(all_rails)
            },
            "connection_map": connection_map,
            "message": f"Loaded {len(all_rails)} power rails with connection mappings"
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Failed to parse JSON: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load knowledge base: {str(e)}"
        }
